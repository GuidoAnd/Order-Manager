# Navegación y acciones de artículos — v0.2

Fecha UTC: **2026-10-01T14:22:11Z**. Resultado: **PASS**.

## Alcance y resultados

- «Menú» desplegable hasta 1023 px; enlaces visibles desde 1024 px.
- Acceso a Dashboard, Jornada, Órdenes, Artículos y Registros; apertura y cierre
  por teclado, controles táctiles de al menos 44 px y una sola navegación visible.
- «Acciones» por artículo: Editar y Eliminar ocultos inicialmente, colores
  distintos y conservación de la búsqueda tras guardar o eliminar.
- Flujo principal completo y ausencia de desborde horizontal de página en
  320x568, 375x667, 430x932, 768x1024 y 1366x768. Cambio de menú comprobado
  entre 1023 y 1024 px. Las tablas de estadísticas mantienen su desplazamiento interno.

| Ejecución | Resultado |
| --- | --- |
| Pruebas nuevas de navegación y acciones | 7 PASS, 20.63 s |
| Suite completa | 114 PASS, 134.69 s |
| Desglose completo | 74 unitarias/integrales y 40 de navegador |
| Formato: git diff --check | PASS |

La primera ejecución focalizada tuvo 6 fallos por supuestos de las pruebas:
una URL de búsqueda sin codificar y el título de Registros. Se corrigieron los
supuestos y se repitió la validación; el flujo móvil existente pasó en esa ejecución.

## Limitaciones

Chromium emulado; no representa pruebas en dispositivos físicos u otros motores.
Los resultados corresponden a los cambios actuales de v0.2 en desarrollo.
