# Catálogo vendido y Registros paginados — v0.2

Fecha UTC: **2026-10-01T17:24:05Z**. Resultado: **PASS**.

## Alcance

- Dos filas hasta 374 px, tres hasta 650 px, cuatro hasta 1023 px y cinco
  desde 1024 px, con Anterior/Siguiente y una sola vista visible.
- Catálogo vendido ordenado por unidades descendentes, conservando nombre,
  unidades e importe. Página independiente de los artículos disponibles;
  filtros y páginas conservados al navegar, editar, guardar y validar errores.
- Registros del más reciente al más antiguo, con Fecha, Acción y Detalle;
  estados vacíos, páginas acotadas y exclusión de jornadas anteriores.
- Todas las filas se recorren sin omisiones ni duplicados. Las consultas
  no modifican datos y la exportación mantiene toda la jornada.
- Fichas móviles, textos largos, ausencia de desborde de página o tabla y
  controles de al menos 44 px en 320x568, 375x667, 430x932, 768x1024 y 1366x768.

## Resultados

- Pruebas focalizadas: **15 PASS, 14.88 s** (10 unitarias/integrales y 5 de navegador).
- Suite completa compartida con el formato JSON: **166 PASS, 179.77 s**
  (111 unitarias/integrales y 55 de navegador).
- `git diff --check`: PASS.

## Limitaciones

Chromium emulado; no constituye validación en dispositivos físicos ni en otros motores.
