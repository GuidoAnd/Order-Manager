# Gestor de órdenes

Aplicación web MVP para que un supervisor gestione jornadas, autores, órdenes y artículos. Cada orden admite varios artículos con cantidad y precio unitario. Calcula totales y estadísticas, y permite exportar la jornada en JSON, CSV resumen y CSV detallado, individualmente o juntos en ZIP.

La aplicación está planteada con FastAPI y Uvicorn y una interfaz HTML/CSS. La jornada, el catálogo, los acumulados y la última exportación se guardan en revisiones JSON locales y se recuperan tras reiniciar. La aplicación no incluye autenticación ni una base de datos compartida.

## Versiones

| Versión | Estado | Descripción |
| --- | --- | --- |
| v0.1 | Implementada | Módulos integrados de jornadas, autores, órdenes, artículos, ventas y estadísticas. |
| v0.2 | Implementada; revisión final documentada | Inventario persistente, resultados por autor, interfaz móvil paginada, órdenes no facturadas y exportación JSON, dos CSV o ZIP. |
| v0.3 | Implementada; cierre documentado | Persistencia por acción, rollback y logging configurable; healthcheck, seguridad local y frontend Jinja2; empaquetado Docker multiarquitectura. |
| v0.3.1 | En desarrollo | Correcciones del editor y mejoras de selección de artículos, avisos y búsqueda de órdenes. |
| v1.0 | Planificada | Versión final prevista del MVP. |

La versión actual es v0.3; la API expone `0.3`. Su cierre se documentó el
2026-10-18, con **501 pruebas aprobadas**, sin fallos, errores ni omisiones.
El [resumen de versión](docs/version/v0_3.md) describe el alcance y la
[validación final](docs/tests/v0_3/V0_3_FINAL_REVIEW_20261018T221853Z.md).
El cierre permite elegir JSON, CSV resumen, CSV detallado o los tres en ZIP.
Registros permite repetir la última descarga sin volver a contabilizar ventas.

## Documentación

- [Resumen de v0.1](docs/version/v0_1.md)
- [Resumen de v0.2](docs/version/v0_2.md)
- [Arquitectura](docs/ARQUITECTURE.md)
- [Persistencia y recuperación](docs/arquitecture/PERSISTENCIA.md)
- [Logging y troubleshooting](docs/arquitecture/LOGGING.md)
- [Healthcheck y script operativo](docs/arquitecture/HEALTHCHECK.md)
- [Seguridad para uso local](docs/arquitecture/SEGURIDAD.md)
- [Interfaz, series y plantillas](docs/arquitecture/FRONTEND.md)
- [Docker y montaje configurable](docs/arquitecture/DOCKER.md)
- [Decisiones técnicas](docs/decisions/) — motivos, alternativas y consecuencias de cambios importantes.
- [Informes de pruebas por versión](docs/tests/README.md)
- [Auditorías](docs/audits/)

La seguridad actual limita solicitudes y protege formularios; no autentica al
supervisor. Se admite acceso temporal desde una LAN mediante hosts explícitos;
las etapas con identidad, sesiones y control de conflictos continúan previstas en
el [ADR de seguridad](docs/decisions/ADR-005-seguridad-local-y-escalabilidad.md).

## Desarrollo local

Requiere Python 3.13.5. `requirements.txt` fija las dependencias de ejecución;
`requirements-test-dev.txt` agrega las herramientas de pruebas y desarrollo.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn order_manager.api:app --host 127.0.0.1 --port 8000
```

Para preparar el entorno de pruebas y desarrollo, instalar
`requirements-test-dev.txt` en lugar de `requirements.txt`.

Las herramientas ASGI que requieren un módulo en la raíz pueden importar `app`
desde `api.py`; ese archivo expone la misma aplicación.

La ruta de datos se configura mediante `DATA_DIR`; por defecto se usa `data/`
junto al código, independientemente del directorio de lanzamiento. Por ejemplo:

```bash
DATA_DIR=/ruta/datos .venv/bin/python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

Cada acción válida confirma su revisión antes de responder éxito. El reinicio
restaura jornada, catálogo, acumulados y descarga. La recuperación del último
cierre exige confirmación y conserva el catálogo vigente; consultar
[persistencia](docs/arquitecture/PERSISTENCIA.md).

Mantener una instancia y un worker; los datos están excluidos de Git. El diagnóstico
usa INFO por defecto y `LOG_LEVEL=DEBUG` para troubleshooting; consultar
[logging](docs/arquitecture/LOGGING.md). Las pruebas e informes se organizan en
[docs/tests](docs/tests/README.md).

## Despliegue con Docker

Requiere Docker Engine y el plugin Docker Compose en el equipo de despliegue.
Ejecutar desde la raíz del repositorio. El Dockerfile utiliza Python 3.13.16
sobre Alpine 3.23 y admite equipos modernos `amd64` y `arm64`; Compose construye
la imagen correspondiente a la arquitectura del equipo.

Preparar la configuración del administrador:

```bash
cp deployment.env.example deployment.env
```

Editar `deployment.env`: `HOST_DATA_DIR` elige el directorio absoluto del host;
`CONTAINER_DATA_DIR` indica dónde se monta dentro del contenedor y configura
`DATA_DIR` automáticamente. `APP_UID` y `APP_GID` definen el usuario sin
privilegios, `APP_PORT` el puerto y `LOG_LEVEL` admite INFO o DEBUG.
El archivo de configuración está excluido de Git. Para configurar el acceso desde
otros equipos, consultar [SEGURIDAD.md](docs/arquitecture/SEGURIDAD.md#excepción-temporal-de-hosts).

Crear el directorio de datos con permisos para el usuario elegido. Para los
valores del ejemplo (`/srv/order-manager/data`, UID/GID `10001`):

```bash
sudo install -d -m 0750 -o 10001 -g 10001 /srv/order-manager/data
```

Si se modifican la ruta o los identificadores, ajustar ese comando a los valores
configurados. El contenedor exige que el directorio exista y sea escribible;
no cambia sus propietarios durante el arranque.

Comprobar la configuración, construir la imagen y levantar el contenedor:

```bash
docker compose --env-file deployment.env -f compose.json config
docker compose --env-file deployment.env -f compose.json build
docker compose --env-file deployment.env -f compose.json up -d
```

Abrir **http://127.0.0.1:8000**; si se cambia `APP_PORT`, usar ese puerto.
El acceso predeterminado queda limitado al equipo local, con una instancia y un worker.
La jornada, el inventario, las exportaciones y los logs permanecen en
`HOST_DATA_DIR` al reemplazar el contenedor.

Consultar el estado y los logs, o detener el despliegue:

```bash
docker compose --env-file deployment.env -f compose.json ps
docker compose --env-file deployment.env -f compose.json logs --tail 100
docker compose --env-file deployment.env -f compose.json down
```

El contenedor incluye healthcheck. Para troubleshooting, configurar
`LOG_LEVEL=DEBUG` y volver a ejecutar `up -d` para aplicar el cambio.
`down` conserva el directorio de datos del host; respaldarlo por separado.
Consultar [Docker y datos persistentes](docs/arquitecture/DOCKER.md) para construcción
multiarquitectura, permisos y copias de seguridad.

## Comentarios

La aplicación, en su versión v0.3, fue probada en producción. La simplicidad de
su despliegue y de la configuración de infraestructura facilitó su puesta en
marcha. Su uso permitió reducir el tiempo dedicado a la gestión de órdenes en
comparación con el método anterior.
