# Jornada, subtotales y órdenes compartidas — v0.2

Fecha UTC: **2026-10-01T16:36:46Z**. Resultado: **PASS**.

## Alcance

- Tablas de órdenes, subtotales y artículos por autor: 2 a 5 filas según ancho,
  Anterior/Siguiente independientes, estados vacíos y páginas acotadas.
- Subtotales por bloques de hasta diez órdenes, incluidos bloques incompletos,
  cantidad y desplegable con números reales. Caso aa: #1, #2, #5; b: #3, #4.
- Subtotales recalculados tras editar/eliminar; acumulados completos conservados.
- Página compartida de Órdenes: reserva una orden de cada autor pendiente,
  amplía el límite base cuando hace falta y no omite ni duplica órdenes.
- Búsqueda de cinco resultados en todos los anchos, nombres numéricos y modo
  exclusivo de número con #90. Edición, eliminación y errores conservan contexto.
- «Acciones» despliega Editar/Eliminar con colores distintos y controles de 44 px.
- Presentación de fichas en móvil, números desplegables operables por teclado,
  nombres largos y ausencia de desbordes de página en 320x568, 375x667,
  430x932, 768x1024 y 1366x768.

## Resultados

| Ejecución | Resultado |
| --- | --- |
| Regresiones de artículos por autor, Órdenes y flujo móvil | 28 PASS, 85.20 s |
| Subtotales y distribución compartida | 23 PASS, 15.15 s |
| Distribución y búsqueda en navegador | 5 PASS, 19.31 s |
| Suite completa | 142 PASS, 160.59 s |
| Desglose completo | 92 unitarias/integrales y 50 de navegador |
| git diff --check | PASS |

La primera ejecución nueva detectó cinco fallos de desborde con nombres largos.
Se corrigieron el ancho mínimo de la cuadrícula de autores y la partición de
sus nombres, y se repitieron las pruebas focalizadas y la suite completa.

## Limitaciones

Chromium emulado; no cubre dispositivos físicos ni otros motores. Los informes
anteriores conservan su alcance histórico: la paginación de Jornada y la
búsqueda reflejan ahora las reglas descritas en este informe.
