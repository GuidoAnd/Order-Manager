# Gestor de órdenes

Aplicación web MVP para que un supervisor gestione jornadas, autores, órdenes y artículos. Cada orden admite varios artículos con cantidad y precio unitario. Calcula totales y estadísticas, y permite exportar los datos de la jornada en formato JSON.

La aplicación está planteada con FastAPI y Uvicorn y una interfaz HTML/CSS. Para v0.1, los datos de jornada serán temporales en memoria y las estadísticas globales se guardarán en un archivo JSON local. La autenticación y la persistencia de permisos del supervisor quedan para una actualización menor posterior. MariaDB y la exportación CSV se mantienen previstas para futuras etapas.

## Versiones

| Versión | Estado | Descripción |
| --- | --- | --- |
| v0.1 | En desarrollo | MVP en desarrollo: módulos integrados de jornadas, autores, órdenes, artículos, ventas y estadísticas; sin inventario inicial. |
| v1.0 | Planificada | Versión final prevista del MVP. |

## Documentación

- [Resumen de v0.1](docs/version/v0_1.md)
- [Arquitectura](docs/ARQUITECTURE.md)
- [Informes de pruebas](docs/tests/)
- [Auditorías](docs/audits/)

## Desarrollo local

Requiere Python 3.13.5. Las versiones exactas de todas las dependencias están en `requirements.txt`.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn order_manager.api:app --host 127.0.0.1 --port 8000
```

La jornada activa y la última exportación se mantienen en memoria. Las estadísticas globales se guardan en `data/global_stats.json`, excluido de Git. Los informes de resultados de pruebas se encuentran en `docs/tests/`.
