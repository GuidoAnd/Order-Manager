# Resultados de pruebas por versión

Actualizado: **2026-10-02T13:55:35Z** (UTC).

Los informes se agrupan según la versión evaluada. Cada archivo conserva su
fecha UTC, alcance y resultado PASS/FAIL. Son registros históricos: sus cantidades
no se suman ni implican que una versión en desarrollo esté terminada.

| Versión | Directorio | Resumen de resultados |
| --- | --- | --- |
| v0.1 | [v0_1/](v0_1/) | Revisión final PASS: 22 pruebas funcionales e integrales de jornadas, autores, órdenes, artículos, estadísticas y cierre JSON. |
| v0.2, revisión final | [v0_2/](v0_2/) | Suite completa: 285 PASS (215 unitarias/integrales y 70 de navegador), en 205,96 s. Incluye flujo principal, interfaz desde 320 px, exportación JSON/dos CSV/ZIP y regresiones de validación numérica, formularios antiguos y categorías. |

## v0.1

- [Pruebas iniciales](v0_1/V01_TESTS_2026-09-25T043830Z.md).
- [Formato del código](v0_1/CODE_FORMAT_2026-09-25T235229Z.md).
- [Botones y acciones](v0_1/UI_ACTION_BUTTONS_2026-09-26T003503Z.md).
- [Interfaz de autores](v0_1/AUTHORS_UI_20260926.md).
- [Cierre de jornada](v0_1/JOURNEY_FINISH_20260926.md).
- [Suite funcional e integral](v0_1/TESTS_WORKSPACE_20260926.md).
- [Revisión final](v0_1/V0_1_FINAL_REVIEW_20260926T035353Z.md).

## v0.2

Incluye las comprobaciones de transición posteriores a la revisión de v0.1 y
las funcionalidades y correcciones de la versión actual.

- [Revisión final de v0.2: 285 PASS](v0_2/V0_2_FINAL_REVIEW_20261002T133719Z.md).
- El mismo informe registra 120 regresiones PASS tras fijar los metadatos de API
  y OpenAPI a `0.2`.
- [Auditoría de errores y optimización](../audits/ERRORES_OPTIMIZACION_20261002T052323Z.md).

- [Catálogo vendido](v0_2/SOLD_CATALOG_20260929T150059Z.md).
- [Entrada ASGI](v0_2/ROOT_API_ENTRYPOINT_20260929T151500Z.md).
- [Inventario y resultados por autor](v0_2/V0_2_INVENTORY_AUTHORS_20260929T154633Z.md).
- [Pruebas móviles iniciales](v0_2/MOBILE_20260929T172038Z.md).
- [Separación de dependencias](v0_2/DEPENDENCY_SPLIT_20260929T175026Z.md).
- [Regresiones y validación móvil](v0_2/MOBILE_FIX_20260930T005124Z.md).
- [Radios en órdenes](v0_2/ORDER_RADIOS_20260930T021846Z.md).
- [Búsqueda de artículos y fichas](v0_2/ARTICLE_BROWSER_20260930T032213Z.md).
- [Ajustes adaptables de Artículos](v0_2/ARTICLES_RESPONSIVE_20260930T043731Z.md).
- [Corrección de listas repetidas](v0_2/ARTICLE_LIST_VISIBILITY_20260930T045405Z.md).
- [Edición del nombre de jornada](v0_2/JOURNEY_NAME_EDITOR_20261001T034449Z.md).

- [Formularios de autores](v0_2/AUTHOR_EDITORS_20261001T035928Z.md).

- [Paginación y búsqueda de órdenes](v0_2/ORDER_BROWSER_20261001T042031Z.md).

- [Artículos por autor en Jornada](v0_2/AUTHOR_ARTICLE_PAGES_20261001T045202Z.md).

- [Navegación y acciones de artículos](v0_2/NAVIGATION_ARTICLE_ACTIONS_20261001T142211Z.md).

- [Jornada, subtotales y órdenes compartidas](v0_2/JOURNEY_SUBTOTALS_SHARED_ORDERS_20261001T163646Z.md).

- [Formato JSON de jornada](v0_2/JOURNEY_JSON_FORMAT_20261001T172405Z.md).

- [Catálogo vendido y Registros](v0_2/SOLD_CATALOG_RECORDS_PAGES_20261001T172405Z.md).

- [Órdenes no facturadas](v0_2/NOT_BILLED_ORDERS_20261001T181054Z.md).

- [CSV y selección de descargas](v0_2/CSV_DOWNLOAD_CHOICES_20261002T044931Z.md).

- [Descargas compactas en Registros](v0_2/RECORDS_DOWNLOAD_COLLAPSE_20261002T050541Z.md).

Las pruebas de navegador documentadas usan Chromium emulado; sus resultados no
constituyen validación en dispositivos físicos o en otros motores.

## Auditorías

Los resultados de las auditorías están en [docs/audits](../audits/).
