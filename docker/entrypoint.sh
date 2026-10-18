#!/bin/sh
set -eu

case "${DATA_DIR:-}" in
    /*) ;;
    *) printf '%s\n' 'DATA_DIR debe ser una ruta absoluta.' >&2; exit 64 ;;
esac
if [ "$#" -eq 0 ]; then
    printf '%s\n' 'Falta el comando de ejecución.' >&2
    exit 64
fi
if ! python3 - "$DATA_DIR" <<'PY'
import os
import sys
import tempfile

try:
    with tempfile.NamedTemporaryFile(dir=sys.argv[1], prefix=".startup-check-") as probe:
        probe.write(b"order-manager")
        probe.flush()
        os.fsync(probe.fileno())
        probe.seek(0)
        if probe.read() != b"order-manager":
            raise OSError("Lectura de comprobación inválida.")
except OSError:
    raise SystemExit(1) from None
PY
then
    printf '%s\n' 'DATA_DIR debe existir y permitir crear, escribir, sincronizar, leer y eliminar archivos al usuario de la aplicación.' >&2
    exit 64
fi
exec "$@"
