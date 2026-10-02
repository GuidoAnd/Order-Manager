# CSV y selección de descargas — v0.2

Fecha UTC: **2026-10-02T04:49:31Z**. Resultado final: **PASS**.

## Alcance

- CSV resumen con artículos y unidades en dos filas por categoría; CSV detallado
  con categoría, subcategoría, artículo, unidades e importe.
- Agregación de autores, productos nuevos, cantidades y precios de líneas
  guardadas; exclusión de regalos/cancelaciones e inventario sin ventas.
- CSV vacíos, nombres repetidos entre categorías/subcategorías, barras,
  separadores, comillas, saltos de línea, acentos y textos de apariencia de fórmula.
- UTF-8 con BOM, punto y coma, encabezados y ancho rectangular del resumen.
- ZIP con exactamente los dos CSV y el JSON, idénticos a las descargas individuales.
- Endpoint JSON compatible, validación de formato y de ID, conservación de la
  descarga anterior al abrir otra jornada y pérdida de disponibilidad al reiniciar.
- Cierre con redirección GET al selector; cancelación, elección exclusiva mediante
  radios, descarga de los cuatro formatos, recarga y acceso desde Registros.
- Descargas repetidas sin nuevas ventas contabilizadas ni escritura de acumulados.
- Formularios sin JS y sin desborde en 320x568, 375x667, 430x932, 768x1024
  y 1366x768; etiquetas táctiles de al menos 44 px.

## Resultados

| Ejecución | Resultado |
| --- | --- |
| Exportación, cierre y regresiones unitarias/integrales | 53 PASS, 2.29 s |
| Selector y cuatro descargas en navegador | 5 PASS, 14.97 s |
| Suite completa final | 204 PASS, 203.67 s |
| Desglose final | 139 unitarias/integrales y 65 de navegador |
| git diff --check | PASS |

Las ejecuciones iniciales detectaron una llamada incorrecta al editor del
catálogo en la preparación de datos y expectativas del antiguo cierre sin
redirección. Se corrigieron los tests y se repitieron. La prueba de recarga
también se ajustó para visitar la URL GET real: el adaptador ASGI sigue el 303
internamente y no actualiza por sí mismo la URL del navegador. La validación
HTTP comprueba la redirección y su destino.

## Limitaciones

Chromium emulado; no representa dispositivos físicos ni otros motores.
Las pruebas comprueban archivos y contenido, no la importación en Excel o
LibreOffice. La última exportación y la generación de archivos permanecen
en memoria; no se evaluaron volúmenes masivos ni almacenamiento histórico.
