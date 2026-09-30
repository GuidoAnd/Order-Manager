# Gestor de órdenes

Aplicación web MVP para que un supervisor gestione jornadas, autores, órdenes y artículos. Cada orden admite varios artículos con cantidad y precio unitario. Calcula totales y estadísticas, y permite exportar los datos de la jornada en formato JSON.

La aplicación está planteada con FastAPI y Uvicorn y una interfaz HTML/CSS. Los datos de jornada son temporales en memoria; las estadísticas globales y el inventario de artículos se guardan en archivos JSON locales. La autenticación y la persistencia de permisos del supervisor quedan para una actualización menor posterior. MariaDB y la exportación CSV se mantienen previstas para futuras etapas.

## Versiones

| Versión | Estado | Descripción |
| --- | --- | --- |
| v0.1 | Implementada | Módulos integrados de jornadas, autores, órdenes, artículos, ventas y estadísticas. |
| v0.2 | En desarrollo | Inventario inicial persistente, artículos temporales reutilizables durante la jornada y resultados separados por autor. |
| v1.0 | Planificada | Versión final prevista del MVP. |

Los cambios publicados ahora son un avance de v0.2. Seguimos trabajando en la
exportación CSV, la navegación móvil y los ajustes de la jornada antes de dar
esta versión por terminada.

## Documentación

- [Resumen de v0.1](docs/version/v0_1.md)
- [Avances de v0.2](docs/version/v0_2.md)
- [Arquitectura](docs/ARQUITECTURE.md)
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

La jornada activa y la última exportación se mantienen en memoria. Las estadísticas globales se guardan en `data/global_stats.json` y el catálogo en `data/inventory.json`; ambos archivos están excluidos de Git. Los informes de resultados se agrupan por versión en [docs/tests](docs/tests/README.md).
