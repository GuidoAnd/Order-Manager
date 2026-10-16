"""Controles HTTP con hosts explícitos y protección de formularios."""

from contextvars import ContextVar
from html import escape
from ipaddress import ip_address
import logging
import re
from secrets import compare_digest
from urllib.parse import parse_qs, urlsplit

from starlette.responses import JSONResponse

from .input_validation import bounded_text


MAX_BODY = 65536
MAX_URL = 8192
MAX_FIELDS = 4096
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
HOST_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
FORM_TOKEN = ContextVar("form_token", default="")
CSP = (
    "default-src 'none'; script-src 'none'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self'; font-src 'self'; connect-src 'none'; "
    "form-action 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'"
)


def normalize_host(host: str) -> str:
    host = host.lower()
    try:
        return str(ip_address(host))
    except ValueError:
        if len(host) > 253 or not all(HOST_LABEL.fullmatch(label) for label in host.split(".")):
            raise ValueError("Host inválido.") from None
        return host


def parse_allowed_hosts(value: str) -> frozenset[str]:
    hosts = set(LOCAL_HOSTS)
    for item in value.split(","):
        if item.strip():
            try:
                hosts.add(normalize_host(item.strip()))
            except ValueError:
                raise ValueError("ALLOWED_HOSTS requiere IP o nombres de host, sin URL, puerto ni comodines.") from None
    return frozenset(hosts)


def protect_forms(content: str) -> str:
    token = FORM_TOKEN.get()
    if not token:
        return content
    field = f'<input type="hidden" name="csrf_token" value="{escape(token, quote=True)}">'
    return re.sub(r'(<form\b[^>]*\bmethod="post"[^>]*>)',
                  lambda match: match[0] + field, content, flags=re.IGNORECASE)


def origin(url: str) -> tuple[str, str, int]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Origen inválido.")
    return parsed.scheme, parsed.hostname.lower(), parsed.port or (443 if parsed.scheme == "https" else 80)


class LocalSecurity:
    def __init__(self, app, token: str, runtime, allowed_hosts: frozenset[str]):
        self.app = app
        self.token = token
        self.runtime = runtime
        self.allowed_hosts = allowed_hosts

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def secured_send(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend([
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"same-origin"),
                    (b"content-security-policy", CSP.encode()),
                ])
                if not scope["path"].startswith("/static/"):
                    headers.append((b"cache-control", b"no-store"))
                message = {**message, "headers": headers}
            await send(message)

        async def reject(status, detail):
            self.runtime.record(logging.WARNING, "Solicitud rechazada por seguridad.",
                                "security_rejected", status=status, method=scope["method"])
            await JSONResponse({"detail": detail}, status_code=status)(scope, receive, secured_send)

        headers = {}
        for key, value in scope.get("headers", []):
            key = key.lower()
            if key in headers and key in {b"host", b"origin", b"content-length", b"content-type"}:
                return await reject(400, "Cabeceras duplicadas no permitidas.")
            headers[key] = value.decode("latin-1")
        server, port = scope.get("server") or ("localhost", 80)
        authority = headers.get(b"host", f'[{server}]:{port}' if ":" in server else f"{server}:{port}")
        if any(char in authority for char in "/?#\\@") or any(char.isspace() for char in authority):
            return await reject(400, "Host inválido.")
        try:
            target = origin(f'{scope.get("scheme", "http")}://{authority}')
            hostname = normalize_host(target[1])
        except ValueError:
            return await reject(400, "Host inválido.")
        if hostname not in self.allowed_hosts:
            return await reject(400, "Host no permitido para esta instancia.")
        if len(scope.get("raw_path", b"")) + len(scope.get("query_string", b"")) > MAX_URL:
            return await reject(414, "Dirección demasiado larga.")
        try:
            query = parse_qs(scope.get("query_string", b"").decode("utf-8"),
                             keep_blank_values=True, max_num_fields=MAX_FIELDS, errors="strict")
            for name in ("q", "category", "subcategory"):
                for value in query.get(name, []):
                    bounded_text(value, "Filtro")
        except (UnicodeError, ValueError):
            return await reject(400, "Filtros inválidos o demasiado largos.")

        mutating = scope["method"] not in {"GET", "HEAD", "OPTIONS"}
        if mutating:
            if headers.get(b"sec-fetch-site") == "cross-site":
                return await reject(403, "Origen de solicitud no permitido.")
            source = headers.get(b"origin") or headers.get(b"referer")
            if source:
                try:
                    if origin(source) != target:
                        raise ValueError("Origen distinto.")
                except ValueError:
                    return await reject(403, "Origen de solicitud no permitido.")
            length = headers.get(b"content-length")
            if length is not None:
                if not length.isdecimal():
                    return await reject(400, "Tamaño de solicitud inválido.")
                if len(length) > 10 or int(length) > MAX_BODY:
                    return await reject(413, "Solicitud demasiado grande.")

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > MAX_BODY:
                return await reject(413, "Solicitud demasiado grande.")
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        body = bytes(body)
        media_type = headers.get(b"content-type", "").split(";", 1)[0].strip().lower()
        if mutating and scope["path"].startswith("/api/") and body and media_type != "application/json":
            return await reject(415, "La API requiere application/json.")
        if mutating and scope["path"].startswith("/ui/"):
            if media_type != "application/x-www-form-urlencoded":
                return await reject(415, "Formato de formulario no permitido.")
            try:
                values = parse_qs(body.decode("utf-8"), keep_blank_values=True,
                                  max_num_fields=MAX_FIELDS, errors="strict")
            except (UnicodeError, ValueError):
                return await reject(400, "Formulario inválido.")
            tokens = values.get("csrf_token", [])
            if len(tokens) != 1 or not compare_digest(tokens[0].encode(), self.token.encode()):
                return await reject(403, "Formulario vencido o inválido. Recargue la página.")
            if any(len(items) != 1 for items in values.values()):
                return await reject(400, "Campos duplicados no permitidos.")

        received = False

        async def replay():
            nonlocal received
            if not received:
                received = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        context = FORM_TOKEN.set(self.token)
        try:
            await self.app(scope, replay, secured_send)
        finally:
            FORM_TOKEN.reset(context)
