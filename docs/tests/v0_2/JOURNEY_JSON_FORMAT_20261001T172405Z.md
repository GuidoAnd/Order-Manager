# Formato JSON de jornada — v0.2

Fecha UTC: **2026-10-01T17:24:05Z**. Resultado: **PASS**.

## Alcance

- Descarga sin inventario inicial completo ni contador interno; identificador
  de formato v0.2, metadatos, autores, órdenes, estadísticas y eventos.
- Altas de catálogo, incluidas no vendidas o posteriormente eliminadas;
  temporales nuevos derivados de órdenes vigentes.
- Cambios sucesivos y revertidos de precio, valores nulos/cero y guardados
  sin cambios. Conservación de los precios facturados por orden.
- Artículos iniciales renombrados/eliminados no se confunden con altas.
- Escrituras fallidas no registran actividad; cierre fallido conserva datos
  para reintentar. Nueva jornada y descarte reinician esa actividad.
- Descarga por API idéntica a la exportación generada.

## Resultados

- Pruebas nuevas del formato: 9 PASS.
- Formato y regresiones de cierre/inventario: 45 PASS, 2.49 s.
- Suite completa compartida con los ajustes de tablas: **166 PASS, 179.77 s**
  (111 unitarias/integrales y 55 de navegador).
- `git diff --check`: PASS.

El [formato documentado](../../version/v0_2.md#json-descargado) corresponde a esta descarga.
La jornada y el historial de sus cambios siguen siendo temporales en memoria;
las órdenes exportadas representan su estado vigente al cierre.
