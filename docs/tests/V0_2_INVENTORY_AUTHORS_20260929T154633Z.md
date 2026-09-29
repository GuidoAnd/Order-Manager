# Inventario inicial y resultados por autor

**Fecha:** 2026-09-29 15:46:33 UTC

| Comprobación | Resultado |
| --- | --- |
| Catálogo inicial: 7 categorías, 21 subcategorías y 68 artículos | PASS |
| Persistencia de altas y cambios de precio; órdenes previas conservan el precio | PASS |
| Artículos sin precio: importe requerido al facturar | PASS |
| Artículos nuevos seleccionables mientras se facturan, retirados al editar o borrar la última orden | PASS |
| Artículos temporales conservados en el JSON y acumulados tras el cierre | PASS |
| Órdenes y estadísticas separadas por autor | PASS |
| API de inventario y orden con precio pendiente | PASS |
| Suite unitaria e integral | PASS: 30 pruebas en 0,82 s |
| Sintaxis Python y `git diff --check` | PASS |

La suite incluye los casos existentes y los nuevos de v0.2.
