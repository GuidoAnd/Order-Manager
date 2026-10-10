"""Revisiones JSON coherentes, publicadas mediante un manifiesto atómico."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import logging
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from uuid import uuid4

from .state_validation import validate_state

COMPONENTS = ("inventory", "global_stats", "journey", "rollback", "last_export", "operation")
ID_PATTERN = re.compile(r"[0-9a-f]{32}\Z")
LOGGER = logging.getLogger(__name__)


class StorageError(Exception):
    pass


class UnsupportedSchema(StorageError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_json(path: Path, value: object) -> None:
    temporary = None
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                prefix=".state-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


class RevisionStorage:
    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        self.manifest: dict | None = None
        self.warnings: list[str] = []
        self.blocked = False

    @property
    def revision(self) -> str:
        return self.manifest["current"]["id"] if self.manifest else ""

    def component_path(self, name: str) -> Path:
        return self.directory / "revisions" / self.revision / f"{name}.json"

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)
            LOGGER.warning(message)

    def read_manifest(self, path: Path) -> dict:
        if path.is_symlink():
            raise ValueError("Manifiesto no válido.")
        value = json.loads(path.read_text(encoding="utf-8"))
        if value["schema"] != 1:
            raise UnsupportedSchema("Esquema persistente no compatible; restaure una versión compatible.")
        for descriptor in (value["current"], value["previous"]):
            if descriptor is not None:
                if not ID_PATTERN.fullmatch(descriptor["id"]):
                    raise ValueError("Identificador de revisión inválido.")
                if set(descriptor["hashes"]) != set(COMPONENTS):
                    raise ValueError("Manifiesto incompleto.")
        return value

    def read_revision(self, descriptor: dict) -> dict:
        state = {}
        for name in COMPONENTS:
            path = self.directory / "revisions" / descriptor["id"] / f"{name}.json"
            try:
                if path.is_symlink() or path.parent.resolve() != path.parent:
                    raise ValueError("Ruta interna no válida.")
                payload = path.read_bytes()
                if sha256(payload).hexdigest() != descriptor["hashes"][name]:
                    raise ValueError("Integridad inválida.")
                document = json.loads(payload)
                if document["schema"] != 1:
                    raise UnsupportedSchema("Esquema persistente no compatible.")
                if document["revision"] != descriptor["id"]:
                    raise ValueError("Referencia de revisión inválida.")
                state[name] = document["value"]
            except UnsupportedSchema:
                raise
            except (OSError, ValueError, KeyError, TypeError):
                if name not in {"rollback", "last_export"}:
                    raise
                state[name] = None
                self.isolate(path)
                self.warn("Snapshot de recuperación no disponible." if name == "rollback"
                          else "La última descarga está dañada y no está disponible.")
        # Los componentes opcionales no deben inutilizar el estado de negocio sano.
        core = {**state, "rollback": None, "last_export": None}
        validate_state(core)
        for component in ("rollback", "last_export"):
            try:
                validate_state({**core, component: state[component]})
            except (ValueError, KeyError, TypeError):
                self.isolate(self.directory / "revisions" / descriptor["id"] / f"{component}.json")
                state[component] = None
                self.warn("Snapshot de recuperación no disponible." if component == "rollback"
                          else "La última descarga está dañada y no está disponible.")
        validate_state(state)
        operation = state["operation"]
        if not ID_PATTERN.fullmatch(operation["id"]) or not isinstance(operation["sequence"], int):
            raise ValueError("Operación inválida.")
        if operation["id"] != descriptor["id"] or operation["sequence"] < 1:
            raise ValueError("Operación inválida.")
        for event in operation["pending_events"]:
            self.event_path(event)
            if (not isinstance(event["sequence"], int) or event["sequence"] > operation["sequence"]
                    or not all(isinstance(event[k], str) and event[k] for k in ("at", "action", "detail", "journey_id"))):
                raise ValueError("Evento inválido.")
        return state

    def isolate(self, path: Path) -> None:
        """Conserva evidencia sin tocar los archivos válidos de otras revisiones."""
        if path.parent.resolve() != path.parent or not path.parent.resolve().is_relative_to(self.directory):
            self.warn("Una ruta interna inválida permanece excluida del uso activo.")
            return
        if not path.is_file():
            return
        try:
            target = self.directory / "damaged" / uuid4().hex
            target.mkdir(parents=True)
            write_json(target / "incident.json", {"at": utc_now(), "file": path.name})
            os.replace(path, target / path.name)
            sync_directory(path.parent)
            sync_directory(target)
        except OSError:
            self.warn("No se pudo aislar el archivo dañado; permanece fuera del uso activo.")

    def load(self) -> dict | None:
        paths = [self.directory / "current.json", self.directory / "current.previous.json"]
        if not any(p.exists() for p in paths):
            if (self.directory / "revisions").exists():
                self.blocked = True
                self.warn("Falta el manifiesto de datos. Restaure una copia válida antes de operar.")
            return None
        for path in paths:
            try:
                manifest = self.read_manifest(path)
            except UnsupportedSchema as error:
                self.blocked = True
                self.warn(str(error))
                return None
            except (OSError, ValueError, KeyError, TypeError):
                self.isolate(path)
                continue
            for key in ("current", "previous"):
                descriptor = manifest[key]
                if descriptor is None:
                    continue
                try:
                    state = self.read_revision(descriptor)
                except UnsupportedSchema as error:
                    self.blocked = True
                    self.warn(str(error))
                    return None
                except (OSError, ValueError, KeyError, TypeError):
                    # Nunca ensamblar componentes de revisiones distintas.
                    for name in COMPONENTS:
                        self.isolate(self.directory / "revisions" / descriptor["id"] / f"{name}.json")
                    continue
                self.manifest = {"schema": 1, "current": descriptor,
                                 "previous": manifest["previous"] if key == "current" else None}
                if path != paths[0] or key != "current":
                    self.warn("Se recuperó la revisión anterior íntegra. La última acción podría no haberse recuperado.")
                self.flush_events(state["operation"].get("pending_events", []))
                return state
        self.blocked = True
        self.warn("No hay una revisión íntegra recuperable. Restaure los datos; las operaciones están bloqueadas.")
        return None

    def commit(self, state: dict, action: str, events: list[dict]) -> dict:
        if self.blocked:
            raise StorageError("El almacenamiento requiere recuperación.")
        validate_state(state)
        revision_id = uuid4().hex
        previous_operation = state.get("operation") or {}
        operation = {"id": revision_id, "sequence": previous_operation.get("sequence", 0) + 1,
                     "action": action, "at": utc_now(), "previous_revision": self.revision,
                     "journey_id": (state["journey"]["data"] or {}).get("id")}
        pending = deepcopy(previous_operation.get("pending_events", []))
        operation["pending_events"] = [e for e in pending if not self.event_saved(e)]
        for index, event in enumerate(events):
            operation["pending_events"].append({**deepcopy(event), "operation_id": revision_id,
                                                 "sequence": operation["sequence"], "index": index})
        state = {**state, "operation": operation}
        revision = self.directory / "revisions" / revision_id
        revision.mkdir(parents=True)
        hashes = {}
        for name in COMPONENTS:
            path = revision / f"{name}.json"
            write_json(path, {"schema": 1, "revision": revision_id, "value": state[name]})
            hashes[name] = sha256(path.read_bytes()).hexdigest()
        sync_directory(revision.parent)
        manifest = {"schema": 1, "current": {"id": revision_id, "hashes": hashes},
                    "previous": self.manifest["current"] if self.manifest else None}
        if self.manifest:
            write_json(self.directory / "current.previous.json",
                       {"schema": 1, "current": self.manifest["current"], "previous": None})
        try:
            write_json(self.directory / "current.json", manifest)
        except OSError as error:
            # os.replace pudo ocurrir antes de fallar el fsync del directorio.
            path = self.directory / "current.json"
            if not path.exists():
                raise
            published = self.read_manifest(path)
            if published != manifest:
                raise
            try:
                sync_directory(self.directory)
            except OSError:
                self.blocked = True
                self.warn("No se pudo confirmar el guardado. Reinicie para verificar la última revisión antes de reintentar.")
                raise StorageError("Resultado del guardado incierto; operaciones bloqueadas hasta verificarlo.") from error
        self.manifest = manifest
        self.flush_events(operation["pending_events"])
        try:
            self.prune()
        except OSError:
            self.warn("No se pudieron recoger revisiones sobrantes; los datos vigentes se conservan.")
        return state

    def event_path(self, event: dict) -> Path:
        if not ID_PATTERN.fullmatch(event["operation_id"]) or type(event["index"]) is not int:
            raise ValueError("Identificador de evento inválido.")
        directory = self.directory / "logs" / "actions"
        if directory.resolve() != directory:
            raise ValueError("Ruta de historial inválida.")
        return directory / f'{event["operation_id"]}-{event["index"]}.json'

    def event_saved(self, event: dict) -> bool:
        try:
            return json.loads(self.event_path(event).read_text()) == event
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def flush_events(self, events: list[dict]) -> None:
        for event in events:
            try:
                if not self.event_saved(event):
                    write_json(self.event_path(event), event)
            except (OSError, ValueError, KeyError, TypeError):
                self.warn("Hay eventos pendientes de guardar en el historial; se reintentará su escritura.")
                return

    def history(self, pending: list[dict]) -> list[dict]:
        events = {}
        for path in (self.directory / "logs" / "actions").glob("*.json"):
            try:
                if path.is_symlink():
                    raise ValueError("Ruta de historial inválida.")
                value = json.loads(path.read_text())
                if (self.event_path(value) != path or type(value["sequence"]) is not int
                        or not all(isinstance(value[k], str) and value[k] for k in ("at", "action", "detail"))):
                    raise ValueError("Evento inválido.")
                events[path.name] = value
            except (OSError, ValueError, KeyError, TypeError):
                self.warn("Un registro del historial está dañado y fue excluido.")
        for event in pending:
            events[self.event_path(event).name] = event
        return sorted(events.values(), key=lambda e: (e["sequence"], e["index"]))

    def prune(self) -> None:
        """Retiene las revisiones referenciadas por ambos manifiestos confirmados."""
        referenced = {self.revision}
        for path in (self.directory / "current.json", self.directory / "current.previous.json"):
            try:
                manifest = self.read_manifest(path)
                referenced.update(d["id"] for d in (manifest["current"], manifest["previous"]) if d)
            except (OSError, StorageError, ValueError, KeyError, TypeError):
                return
        revisions = self.directory / "revisions"
        if revisions.resolve() != revisions:
            return
        for directory in revisions.iterdir():
            if directory.name in referenced or not ID_PATTERN.fullmatch(directory.name) or directory.is_symlink():
                continue
            try:
                files = list(directory.iterdir())
                if any(p.is_symlink() or not p.is_file() or p.name not in
                       {f"{name}.json" for name in COMPONENTS} for p in files):
                    continue
                for path in files:
                    path.unlink()
                directory.rmdir()
            except OSError:
                self.warn("No se pudieron recoger revisiones sobrantes; los datos vigentes se conservan.")
