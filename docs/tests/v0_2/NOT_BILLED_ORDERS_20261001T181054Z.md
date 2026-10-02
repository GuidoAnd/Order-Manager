# Órdenes no facturadas — v0.2

Fecha UTC: **2026-10-01T18:10:54Z**. Resultado final: **PASS**.

## Alcance

- Tipo «No facturada (regalo/cancelada)», independiente del origen de sus artículos.
  Exige autor, al menos un artículo y cantidades positivas; mantiene el límite de
  cincuenta líneas. No admite órdenes sin artículos.
- Precios ocultos en el formulario e ignorados al normalizar estas órdenes:
  precios, subtotales y total nulos. El catálogo conserva sus precios.
- Selección conservada al agregar/quitar líneas, editar y validar errores.
- Órdenes y Jornada muestran la etiqueta y «Sin importe»; Registros identifica
  número, ID y artículos; el JSON conserva estado, cantidades e importes nulos.
- Excluidas de conteo de ventas, unidades, importes, promedios, catálogo vendido,
  subtotales y acumulados globales. Los productos exclusivos de estas órdenes
  no se incorporan al inventario temporal de ventas.
- Cambiar de tipo conserva ID/número y recalcula resultados. Pasar a venta sin
  precios válidos se rechaza sin modificar el estado anterior.
- Flujos completos y descarga JSON en 320x568, 375x667, 430x932, 768x1024 y
  1366x768; sin desborde de página.

## Resultados

| Ejecución | Resultado |
| --- | --- |
| Pruebas funcionales nuevas | 13 PASS, 1.18 s |
| Flujo nuevo en navegador | 5 PASS, 27.66 s |
| Venta normal y no facturada en navegador | 10 PASS, 87.72 s |
| Suite completa final | 184 PASS, 212.75 s |
| Desglose final | 124 unitarias/integrales y 60 de navegador |
| git diff --check | PASS |

La primera suite completa tuvo 179 PASS y 5 FAIL: el test anterior contaba el
nuevo grupo «Tipo de orden» como un artículo. Se acotaron sus selectores a
`.order-line`, se repitieron ambos flujos y luego la suite completa.

## Limitaciones

Chromium emulado; no representa pruebas en dispositivos físicos ni otros motores.
El estado conjunto no distingue regalo de cancelación. Las jornadas cerradas
siguen contando como jornadas; estas órdenes no cuentan como ventas.
