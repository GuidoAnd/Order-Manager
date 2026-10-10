# Gestor de órdenes

Aplicación web MVP para que un supervisor gestione jornadas, autores, órdenes y artículos. Cada orden admite varios artículos con cantidad y precio unitario. Calcula totales y estadísticas, y permite exportar la jornada en JSON, CSV resumen y CSV detallado, individualmente o juntos en ZIP.

La aplicación está planteada con FastAPI y Uvicorn y una interfaz HTML/CSS. La jornada, el catálogo, los acumulados y la última exportación se guardan en revisiones JSON locales y se recuperan tras reiniciar. La autenticación y la persistencia de permisos del supervisor quedan para una actualización menor posterior. MariaDB se mantiene prevista para una etapa posterior.

## Versiones

| Versión | Estado | Descripción |
| --- | --- | --- |
| v0.1 | Implementada | Módulos integrados de jornadas, autores, órdenes, artículos, ventas y estadísticas. |
| v0.2 | Implementada; revisión final documentada | Inventario persistente, resultados por autor, interfaz móvil paginada, órdenes no facturadas y exportación JSON, dos CSV o ZIP. |
| v0.3 | En desarrollo | Persistencia por acción, rollback y logging configurable; healthcheck operativo; seguridad, plantillas y Docker pendientes. |
| v1.0 | Planificada | Versión final prevista del MVP. |

La versión actual de desarrollo es v0.3 del MVP. El primer bloque incorpora
persistencia por acción y rollback; el segundo agrega logging con DEBUG.
El tercer bloque agrega comprobación de salud; seguridad, frontend y Docker
siguen pendientes.
La API identifica esta versión como `0.3`. Consultar el [resumen de v0.3](docs/version/v0_3.md).
La revisión histórica de v0.2 y sus resultados están en el [resumen de v0.2](docs/version/v0_2.md).

Al cerrar la jornada, un selector permite descargar CSV resumen (cantidades por
categoría), CSV detallado (unidades e importe por artículo), JSON completo o los
tres archivos en ZIP. En Registros, «Descargar última jornada» despliega las opciones
para repetir las descargas hasta el siguiente cierre correcto o su recuperación, incluso tras reiniciar,
sin volver a contabilizar ventas.

## Documentación

- [Resumen de v0.1](docs/version/v0_1.md)
- [Resumen de v0.2](docs/version/v0_2.md)
- [Arquitectura](docs/ARQUITECTURE.md)
- [Logging y troubleshooting](docs/LOGGING.md)
- [Healthcheck y script operativo](docs/HEALTHCHECK.md)
- [Decisiones técnicas](docs/decisions/) — motivos, alternativas y consecuencias de cambios importantes.
- [Informes de pruebas por versión](docs/tests/README.md)
- [Auditorías](docs/audits/)

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

Cada modificación válida confirma una revisión coherente antes de responder éxito.
Al reiniciar se restauran jornada, inventario, acumulados y última descarga.
En Jornada, «Recuperar última jornada» abre una advertencia y una confirmación:
reabre la última cerrada al momento anterior al cierre, descarta la abierta si
existe y conserva el catálogo vigente. Los nuevos archivos requieren volver a cerrar.

Se mantiene una sola instancia y un solo worker. Los datos están excluidos de Git.
Un directorio o volumen persistente no sustituye una copia de seguridad.
Consultar [persistencia y recuperación](docs/PERSISTENCIA.md) antes de restaurar datos.
Los informes se agrupan por versión en [docs/tests](docs/tests/README.md).

El diagnóstico se guarda en `DATA_DIR/logs/application.log` y consola, con INFO
por defecto y `LOG_LEVEL=DEBUG` para troubleshooting. Rota a 5 MiB con 5 copias;
el historial de acciones y cierres se conserva íntegro por separado. Consultar
[configuración y comportamiento ante fallos](docs/LOGGING.md).
