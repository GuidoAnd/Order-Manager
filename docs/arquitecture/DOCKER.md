# Docker y datos persistentes

El Dockerfile prepara variantes `linux/amd64` y `linux/arm64` con Python 3.13.16,
Alpine 3.23 e índice oficial fijado por digest. La imagen usa builder/runtime,
venv, plantillas y estáticos, usuario sin privilegios y un worker de Uvicorn.
El entorno local de desarrollo conserva Python 3.13.5.

## Configuración por el administrador

Copiar `deployment.env.example` a `deployment.env`, excluido de Git. Configurar:

| Variable | Significado | Valor de ejemplo |
| --- | --- | --- |
| HOST_DATA_DIR | Directorio absoluto existente del anfitrión | /srv/order-manager/data |
| CONTAINER_DATA_DIR | Destino absoluto del montaje y DATA_DIR | /data |
| APP_UID / APP_GID | Identidad numérica de construcción y ejecución | 10001 / 10001 |
| APP_BIND_HOST | IP del anfitrión donde publicar el puerto | 127.0.0.1 |
| APP_PORT | Puerto de acceso | 8000 |
| ALLOWED_HOSTS | IP o nombres adicionales del servidor, separados por comas | Vacío: solo loopback |
| LOG_LEVEL | Diagnóstico INFO o DEBUG | INFO |

El administrador crea el directorio y asigna permisos de lectura, escritura y
recorrido al UID/GID elegido. Reservar una ruta exclusiva para datos, sin montar
sobre `/app`, `/opt/venv` ni directorios del sistema. El montaje no crea su origen;
el arranque no crea DATA_DIR ni cambia propietarios. Si cambian UID/GID,
reconstruir la imagen y ajustar permisos antes de iniciarla.

Compose usa raíz de solo lectura y `/tmp` temporal; los datos de negocio y logs
viven en DATA_DIR. El puerto se publica en `127.0.0.1` de forma predeterminada.
Para la excepción temporal LAN, configurar `APP_BIND_HOST` con la IP del servidor
y añadir esa IP a `ALLOWED_HOSTS`. Los equipos acceden a `http://IP:APP_PORT`.
Estas variables se aplican al crear el contenedor, sin modificar DATA_DIR.
La aplicación no autentica al supervisor; consultar el
[alcance de la excepción](SEGURIDAD.md#excepción-temporal-de-hosts).

## Comandos de despliegue

Los siguientes comandos son para el entorno Docker del administrador:

```bash
docker compose --env-file deployment.env -f compose.json config
docker compose --env-file deployment.env -f compose.json build
docker compose --env-file deployment.env -f compose.json up -d
docker compose --env-file deployment.env -f compose.json logs --tail 100
```

Compose construye la plataforma nativa. Para producir un archivo OCI con ambas
variantes usando un builder configurado para ellas:

```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  --build-arg APP_UID=10001 --build-arg APP_GID=10001 \
  --tag order-manager:0.3 --output type=oci,dest=order-manager-0.3.oci.tar .
```

El índice selecciona binarios de cada arquitectura. No mezcla ARM y AMD en una
misma ejecución. La variante Atom N270/linux/386 se entrega por separado, fuera
del repositorio de aplicación; su contexto de construcción es la raíz de esta
aplicación y requiere `--platform linux/386`. Compila pydantic-core y MarkupSafe,
con herramientas fijadas y CPU SSE2. La construcción y ejecución de las imágenes corresponden al usuario.

## Salud y conservación de datos

El healthcheck ejecuta `python -m order_manager.healthcheck`, consultando HTTP
local. Un resultado sano o degradado permite salida 0; indisponibilidad devuelve
1. Docker evalúa cada 30 s, con timeout de 15 s, inicio de 20 s y tres fallos
consecutivos. Consultar [healthcheck](HEALTHCHECK.md) y [logging](LOGGING.md).

Mantener una instancia y un worker. No compartir DATA_DIR entre escritores.
Para copia consistente, detener la aplicación y copiar el directorio completo,
incluidos revisiones, manifiesto e historial; restaurarlo con la aplicación
apagada y verificar salud antes de reanudar. Los archivos descargados no
sustituyen esa copia. Consultar [persistencia](PERSISTENCIA.md).

Decisión: [ADR-007](../decisions/ADR-007-docker-y-arquitecturas.md).
Referencias: [montajes Docker](https://docs.docker.com/engine/storage/bind-mounts/)
y [multiarquitectura](https://docs.docker.com/build/building/multi-platform/).
