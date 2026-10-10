"""Script HTTP: python -m order_manager.healthcheck; no inspecciona el host."""
import argparse
import json
import logging
import os
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, ProxyHandler, Request

from .runtime_logging import RuntimeLog


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


def probe(url, timeout):
    opener = build_opener(ProxyHandler({}), NoRedirects())
    try:
        with opener.open(Request(url, headers={"Accept": "application/json"}), timeout=timeout) as response:
            if response.status != 200:
                return "unavailable"
            payload = response.read(65537)
            if len(payload) > 65536:
                return "unavailable"
            document = json.loads(payload)
    except (OSError, HTTPError, URLError, ValueError):
        return "unavailable"
    if (not isinstance(document, dict) or not isinstance(document.get("status"), str)
            or document["status"] not in {"healthy", "degraded"}):
        return "unavailable"
    if document.get("checks") != {"initialized": True, "revision": True, "data_io": True}:
        return "unavailable"
    return document["status"]


def run(url, *, timeout=3.0, attempts=3, delay=1.0):
    for attempt in range(1, attempts + 1):
        status = probe(url, timeout)
        if status != "unavailable":
            return status, attempt
        if attempt < attempts:
            time.sleep(delay)
    return "unavailable", attempts


def main(argv=None):
    parser = argparse.ArgumentParser(description="Comprueba HTTP, revisión persistente y DATA_DIR de Order Manager.")
    parser.add_argument("--url", default=os.environ.get("HEALTHCHECK_URL", "http://127.0.0.1:8000/api/health"))
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args(argv)
    target = urlsplit(args.url)
    if (target.scheme != "http" or target.hostname not in {"127.0.0.1", "localhost", "::1"}
            or target.username or target.password or target.query or target.fragment or target.path != "/api/health"):
        parser.error("La URL debe ser HTTP local, sin credenciales ni query, con ruta /api/health.")
    if not 0 < args.timeout <= 30 or not 1 <= args.attempts <= 10 or not 0 <= args.delay <= 10:
        parser.error("Timeout: 0–30 s; intentos: 1–10; espera: 0–10 s.")
    status, attempts = run(args.url, timeout=args.timeout, attempts=args.attempts, delay=args.delay)
    # El endpoint registra los resultados alcanzables. Un fallo HTTP también necesita evidencia local.
    if status == "unavailable":
        directory = Path(os.environ.get("DATA_DIR") or Path(__file__).resolve().parent.parent / "data").resolve()
        runtime = RuntimeLog(directory, filename="healthcheck.log")
        try:
            runtime.record(logging.ERROR, "La comprobación HTTP no pudo confirmar disponibilidad.",
                           "healthcheck_http_failed", phase=status)
        finally:
            runtime.close()
    print(json.dumps({"status": status, "attempts": attempts}))
    return 1 if status == "unavailable" else 0


if __name__ == "__main__":
    raise SystemExit(main())
