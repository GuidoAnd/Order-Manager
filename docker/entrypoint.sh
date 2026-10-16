#!/bin/sh
set -eu

case "${DATA_DIR:-}" in
    /*) ;;
    *) printf '%s\n' 'DATA_DIR debe ser una ruta absoluta.' >&2; exit 64 ;;
esac
if [ ! -d "$DATA_DIR" ] || [ ! -w "$DATA_DIR" ]; then
    printf '%s\n' 'DATA_DIR debe existir y permitir escritura al usuario de la aplicación.' >&2
    exit 64
fi
if [ "$#" -eq 0 ]; then
    printf '%s\n' 'Falta el comando de ejecución.' >&2
    exit 64
fi
exec "$@"
