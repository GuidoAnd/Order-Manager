# Artículos: catálogo vendido y controles adaptables — v0.2

Timestamp UTC: **2026-09-30T04:37:31Z**.

Resultado: **PASS — 55 pruebas en 52,25 s**: 50 unitarias e integrales y cinco
casos de navegador con JavaScript desactivado.

## Cobertura

- Catálogo vendido: solo nombre, conservando unidades vendidas, importe y orden
  por unidades. Productos de categorías distintas conservan sus totales separados;
  nombres con barras se muestran sin perder caracteres.
- Paginación: todos los artículos son accesibles una sola vez al recorrer las
  páginas de cada tamaño (2, 3, 4 y 5), con filtros y búsqueda conservados.
- Altas y ediciones: desplegables existentes, subcategorías correspondientes,
  conservación de selección al cambiar de categoría y rechazo de categorías
  desconocidas o relaciones inválidas sin modificar el catálogo.
- Acciones de Artículos centradas en móvil, con separación y controles táctiles;
  comprobación de desborde, textos largos, edición y conservación de precios en órdenes.
- Regresión del flujo completo: jornada, autor, órdenes, estadísticas, cierre y JSON.

| Viewport | Resultados por página | Flujo y ancho de página |
| --- | --- | --- |
| 320x568 | 2 | PASS |
| 375x667 | 3 | PASS |
| 430x932 | 3 | PASS |
| 768x1024 | 4 | PASS |
| 1366x768 | 5 | PASS |

También se comprueban los límites 374, 375, 650, 651, 1023 y 1024 px, con una sola
vista de resultados visible y sin desborde horizontal de página.

Ejecución: `python -m pytest -q -p no:cacheprovider`, con bytecode desactivado.
Los primeros intentos detectaron expectativas y selectores antiguos en las pruebas;
se ajustaron al nombre simplificado y a las vistas visibles antes del resultado final.
Validación en Chromium emulado; no incluye dispositivos físicos ni otros motores.
