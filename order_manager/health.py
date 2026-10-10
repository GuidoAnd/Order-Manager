"""Disponibilidad e integridad comprobadas sin modificar datos de negocio."""
from hashlib import sha256
import json
import logging
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from .persistence import COMPONENTS, StorageError, sync_directory
from .state_validation import validate_state


class HealthCheck:
    def __init__(self, store):
        self.store = store
        self.previous_status = None

    def _revision(self):
        storage = self.store.storage
        manifest = storage.read_manifest(storage.directory / "current.json")
        descriptor = manifest["current"]
        if descriptor != storage.manifest["current"]:
            raise ValueError("La revisión de disco no coincide con la revisión activa.")
        state = {}
        optional_damage = []
        for name in COMPONENTS:
            path = storage.directory / "revisions" / descriptor["id"] / f"{name}.json"
            try:
                if path.is_symlink() or path.parent.resolve() != path.parent:
                    raise ValueError("Ruta interna inválida.")
                payload = path.read_bytes()
                if sha256(payload).hexdigest() != descriptor["hashes"][name]:
                    raise ValueError("Integridad inválida.")
                document = json.loads(payload)
                if document["schema"] != 1 or document["revision"] != descriptor["id"]:
                    raise ValueError("Esquema o revisión inválidos.")
                state[name] = document["value"]
            except (OSError, ValueError, KeyError, TypeError):
                if name not in {"rollback", "last_export"}:
                    raise
                state[name] = None
                optional_damage.append(name)
        core = {**state, "rollback": None, "last_export": None}
        validate_state(core)
        for component in ("rollback", "last_export"):
            try:
                validate_state({**core, component: state[component]})
            except (ValueError, KeyError, TypeError):
                optional_damage.append(component)
        return optional_damage

    def _writable(self):
        directory = self.store.data_dir
        temporary = None
        try:
            with NamedTemporaryFile("w+b", dir=directory, prefix=".health-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(b"order-manager-health\n")
                stream.flush()
                os.fsync(stream.fileno())
            sync_directory(directory)
            if temporary.read_bytes() != b"order-manager-health\n":
                raise OSError("Lectura de prueba inválida.")
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
                sync_directory(directory)

    def check(self):
        with self.store.lock:
            issues = []
            checks = {"initialized": not self.store.storage.blocked, "revision": False, "data_io": False}
            if checks["initialized"]:
                try:
                    damaged = self._revision()
                    checks["revision"] = True
                    issues.extend(f"optional_{name}_unavailable" for name in damaged)
                except (OSError, StorageError, ValueError, KeyError, TypeError) as error:
                    self.store.runtime_log.record(logging.ERROR, "Falló la comprobación de datos esenciales.",
                                                  "health_revision_failed", error=error)
                    issues.append("essential_revision_unavailable")
            else:
                issues.append("storage_initialization_failed")
            try:
                self._writable()
                checks["data_io"] = True
            except OSError as error:
                self.store.runtime_log.record(logging.ERROR, "Falló la comprobación de lectura/escritura de DATA_DIR.",
                                              "health_io_failed", error=error)
                issues.append("data_io_failed")
            if self.store.runtime_log.file.failed:
                issues.append("diagnostic_log_unavailable")
            if (self.store._operation or {}).get("pending_events"):
                if any(not self.store.storage.event_saved(e) for e in self.store._operation["pending_events"]):
                    issues.append("history_pending")
            if self.store.storage.warnings:
                issues.append("storage_warning")
            status = "unavailable" if not all(checks.values()) else "degraded" if issues else "healthy"
            signature = (status, tuple(sorted(issues)))
            if signature != self.previous_status or status != "healthy":
                level = logging.ERROR if status == "unavailable" else logging.WARNING if status == "degraded" else logging.INFO
                self.store.runtime_log.record(level, "Resultado de comprobación de salud.", "healthcheck",
                                              phase=status, revision=self.store.storage.revision)
            self.previous_status = signature
            return {"status": status, "checks": checks, "issues": sorted(set(issues))}
