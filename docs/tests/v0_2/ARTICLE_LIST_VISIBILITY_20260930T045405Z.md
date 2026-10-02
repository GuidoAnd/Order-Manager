# Corrección de listas repetidas en Artículos — v0.2

Timestamp UTC: **2026-09-30T04:54:05Z**.

## Resultado

**PASS — 66 pruebas en 69,00 s:** 51 unitarias e integrales y 15 de navegador.
Suite: `python -m pytest -q -p no:cacheprovider`.

## Corrección y comprobaciones

- Se reproduce la repetición: el HTML anterior muestra cuatro vistas cuando el
  CSS no contiene las reglas para ocultarlas.
- La página entrega sus reglas de visibilidad junto al HTML; solo una lista está
  visible aunque la hoja externa sea antigua o no esté disponible.
- La URL del CSS cambia al cambiar su contenido; se verifica que contenido igual
  conserve la URL y contenido distinto genere otra.
- Búsqueda, «Siguiente» y «Anterior» funcionan en cada tamaño. Las páginas
  consecutivas muestran artículos distintos y regresar recupera los anteriores.
- El flujo completo y las comprobaciones de ancho de página siguen aprobados.

| Viewport | Artículos por página | CSS anterior | CSS no disponible |
| --- | --- | --- | --- |
| 320x568 | 2 | PASS | PASS |
| 375x667 | 3 | PASS | PASS |
| 430x932 | 3 | PASS | PASS |
| 768x1024 | 4 | PASS | PASS |
| 1366x768 | 5 | PASS | PASS |

La suite anterior no cubría CSS antiguo o fallos de su descarga. Este informe añade
esa regresión; reproduce una causa posible del problema, sin confirmar el estado
de caché del navegador del usuario. Chromium emulado; no incluye dispositivos físicos.
