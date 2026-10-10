"""Diagnóstico JSON con logging estándar, rotación y contexto sin datos de entrada."""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import sys
from time import perf_counter
import traceback
import weakref

from fastapi.responses import JSONResponse


@dataclass(frozen=True)
class LogConfig:
    level: str = "INFO"
    max_bytes: int = 5 * 1024 * 1024
    backups: int = 5

    def __post_init__(self):
        if self.level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL debe ser DEBUG, INFO, WARNING, ERROR o CRITICAL.")
        if type(self.max_bytes) is not int or self.max_bytes < 1024:
            raise ValueError("LOG_MAX_BYTES debe ser un entero de al menos 1024.")
        if type(self.backups) is not int or not 1 <= self.backups <= 100:
            raise ValueError("LOG_BACKUP_COUNT debe ser un entero entre 1 y 100.")

    @classmethod
    def from_environment(cls):
        try:
            return cls(level=os.environ.get("LOG_LEVEL", "INFO").upper(),
                       max_bytes=int(os.environ.get("LOG_MAX_BYTES", str(5 * 1024 * 1024))),
                       backups=int(os.environ.get("LOG_BACKUP_COUNT", "5")))
        except ValueError:
            raise ValueError("Configuración de logging inválida; revise LOG_LEVEL, LOG_MAX_BYTES y LOG_BACKUP_COUNT.") from None


def safe_traceback(error: BaseException) -> list[dict]:
    """Mantiene ubicación y cadena de errores sin mensajes, código ni locales."""
    result = []
    seen = set()
    while error is not None and id(error) not in seen and len(result) < 8:
        seen.add(id(error))
        result.append({"type": type(error).__name__, "frames": [
            {"file": Path(frame.filename).name, "function": frame.name, "line": frame.lineno}
            for frame in traceback.extract_tb(error.__traceback__)[-20:]
        ]})
        error = error.__cause__ or (None if error.__suppress_context__ else error.__context__)
    return result


class JsonFormatter(logging.Formatter):
    def format(self, record):
        document = {"at": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
                    "level": record.levelname, "message": record.getMessage(),
                    "operation": getattr(record, "operation", "application")}
        for key in ("journey_id", "revision", "operation_id", "event", "method", "route",
                    "status", "duration_ms", "phase", "format", "traceback"):
            value = getattr(record, key, None)
            if value is not None:
                document[key] = value
        return json.dumps(document, ensure_ascii=False, allow_nan=False)


class NonFatalConsoleHandler(logging.StreamHandler):
    def handleError(self, record):
        # Un stderr cerrado tampoco debe interrumpir una operación confirmada.
        pass


class RecoveringFileHandler(RotatingFileHandler):
    """Reintenta abrir el destino tras errores; nunca propaga fallos al negocio."""
    def __init__(self, path, config, console):
        super().__init__(path, maxBytes=config.max_bytes, backupCount=config.backups,
                         encoding="utf-8", delay=True)
        self.console = console
        self.failed = False
        self._failure_reported = False

    def _open(self):
        parent = Path(self.baseFilename).parent
        if parent.is_symlink() or parent.resolve() != parent:
            raise OSError("Ruta de diagnóstico inválida.")
        parent.mkdir(parents=True, exist_ok=True)
        if Path(self.baseFilename).is_symlink():
            raise OSError("Archivo de diagnóstico inválido.")
        return super()._open()

    def emit(self, record):
        was_failed = self.failed
        self.failed = False
        super().emit(record)
        if was_failed and not self.failed:
            self._failure_reported = False
            notice = logging.LogRecord("order_manager", logging.WARNING, "", 0,
                                       "Se recuperó la escritura del diagnóstico persistente.", (), None)
            notice.operation = "logging_recovered"
            self.console.handle(notice)

    def handleError(self, record):
        # El comportamiento predeterminado imprime detalles sin filtrar.
        if self.stream is not None:
            try:
                self.stream.close()
            except OSError:
                pass
            self.stream = None
        self.failed = True
        if self._failure_reported:
            return
        self._failure_reported = True
        notice = logging.LogRecord("order_manager", logging.ERROR, "", 0,
                                   "No se pudo guardar el diagnóstico persistente; la aplicación continúa y reintentará.", (), None)
        notice.operation = "logging_failed"
        self.console.handle(notice)


class RuntimeLog:
    def __init__(self, directory: Path, config: LogConfig | None = None, *, filename="application.log"):
        if filename not in {"application.log", "healthcheck.log"}:
            raise ValueError("Nombre de diagnóstico no permitido.")
        self.config = config or LogConfig.from_environment()
        self.logger = logging.Logger("order_manager", level=self.config.level)
        self.logger.propagate = False
        self.console = NonFatalConsoleHandler(sys.stderr)
        self.console.setFormatter(JsonFormatter())
        self.file = RecoveringFileHandler(directory / "logs" / filename, self.config, self.console)
        self.file.setFormatter(JsonFormatter())
        self.logger.addHandler(self.console)
        self.logger.addHandler(self.file)
        self._finalizer = weakref.finalize(self, self.file.close)

    def record(self, level, message, operation, *, error=None, **context):
        if error is not None:
            context["traceback"] = safe_traceback(error)
        for key in ("journey_id", "revision", "operation_id"):
            value = context.get(key)
            if value is not None and not re.fullmatch(r"[0-9a-f-]{32,36}", str(value)):
                context.pop(key)
        self.logger.log(level, message, extra={"operation": operation, **context})

    def close(self):
        self._finalizer()
        self.console.close()


class RequestDiagnostics:
    """Errores HTTP y tiempos sin URL, query, cabeceras ni cuerpo de usuario."""
    def __init__(self, app, runtime):
        self.app = app
        self.runtime = runtime

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = perf_counter()
        status = 500
        response_started = False

        async def observed_send(message):
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                status = message["status"]
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, observed_send)
        except Exception as error:
            self.runtime.record(logging.ERROR, "Error HTTP inesperado.", "request_failed", error=error,
                                route=getattr(scope.get("route"), "path", "unmatched"), method=scope["method"])
            if response_started:
                raise
            response = JSONResponse({"detail": "Error interno. Revise el diagnóstico de la aplicación."}, status_code=500)
            await response(scope, receive, observed_send)
        finally:
            self.runtime.record(logging.DEBUG, "Solicitud completada.", "request_completed",
                                route=getattr(scope.get("route"), "path", "unmatched"),
                                method=scope["method"], status=status,
                                duration_ms=round((perf_counter() - started) * 1000, 3))
