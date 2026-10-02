# Gestor de órdenes

Aplicación web MVP para que un supervisor gestione jornadas, autores, órdenes y artículos. Cada orden admite varios artículos con cantidad y precio unitario. Calcula totales y estadísticas, y permite exportar la jornada en JSON, CSV resumen y CSV detallado, individualmente o juntos en ZIP.

La aplicación está planteada con FastAPI y Uvicorn y una interfaz HTML/CSS. Los datos de jornada son temporales en memoria; las estadísticas globales y el inventario de artículos se guardan en archivos JSON locales. La autenticación y la persistencia de permisos del supervisor quedan para una actualización menor posterior. MariaDB se mantiene prevista para una etapa posterior.

## Versiones

| Versión | Estado | Descripción |
| --- | --- | --- |
| v0.1 | Implementada | Módulos integrados de jornadas, autores, órdenes, artículos, ventas y estadísticas. |
| v0.2 | Implementada; revisión final documentada | Inventario persistente, resultados por autor, interfaz móvil paginada, órdenes no facturadas y exportación JSON, dos CSV o ZIP. |
| v1.0 | Planificada | Versión final prevista del MVP. |

La versión actual es v0.2 del MVP. Su alcance incluye las correcciones de
validación numérica, formularios antiguos y categorías, además de consultas
del catálogo reutilizadas dentro de cada operación. El estado revisado y los
resultados de validación se detallan en el [resumen de v0.2](docs/version/v0_2.md).
La revisión final del 2026-10-02 pasó 285 pruebas, incluidas 70 de navegador
desde 320 px. La API identifica esta versión como `0.2`.

Al cerrar la jornada, un selector permite descargar CSV resumen (cantidades por
categoría), CSV detallado (unidades e importe por artículo), JSON completo o los
tres archivos en ZIP. En Registros, «Descargar última jornada» despliega las opciones
para repetir las descargas hasta el siguiente cierre correcto o el reinicio,
sin volver a contabilizar ventas.

## Documentación

- [Resumen de v0.1](docs/version/v0_1.md)
- [Resumen de v0.2](docs/version/v0_2.md)
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

La jornada activa y la última exportación se mantienen en memoria y se pierden
al reiniciar. Las estadísticas globales se guardan en `data/global_stats.json`
y el catálogo en `data/inventory.json`; ambos archivos están excluidos de Git.
La arquitectura requiere una sola instancia y un solo proceso de aplicación.
Los informes de resultados se agrupan por versión en [docs/tests](docs/tests/README.md).
