# ADR-003 — Exportación CSV y selección de descargas

## Estado

Aceptada. Actualizada y unificada: reúne la decisión inicial de exportación CSV
y su ampliación de formatos y selección de descargas.

## Fecha

Decisión inicial: 2026-09-29.
Ampliación de formatos y descargas: 2026-10-02.
Actualización: 2026-10-10T18:17:54Z.

## Historial de actualización

- 2026-09-29: se acordó exportar ventas por artículo junto con JSON, sin introducir
  una base de datos SQL; cantidades agregadas desde las líneas de todos los autores.
- 2026-10-02: se definieron dos CSV y selección de CSV, JSON o ZIP después del cierre.
- 2026-10-10T18:17:54Z: se actualizó la documentación de formatos CSV y selección
  de descargas en ADR-003.
- 2026-10-10T19:42:46Z: se actualizó la documentación del selector con persistencia
  del documento de cierre e identificación de descargas en v0.3.

## Contexto

El cierre necesita una presentación rápida de cantidades y otra apta para
filtrar y analizar ventas. Una sola matriz con artículos en columnas se ensancha
al incorporar productos y cambia su estructura entre jornadas. El JSON conserva
órdenes y registros, pero no ofrece una tabla directamente utilizable en planillas.

## Decisión

Ofrecer dos CSV derivados del JSON inmutable del cierre:

- **Resumen:** cada categoría ocupa dos filas. La primera contiene la categoría
  y los artículos con su subcategoría entre corchetes; la segunda contiene
  «Unidades» y sus cantidades. Todas las filas se completan con celdas vacías
  hasta el ancho máximo. Sin ventas, contiene solo «Categoría / artículo».
- **Detallado:** encabezado fijo `Categoría;Subcategoría;Artículo;Unidades;Importe`
  y una fila por combinación exacta de categoría, subcategoría y nombre.
  Sin ventas, conserva únicamente el encabezado.

Ambos reúnen las ventas de todos los autores, incluyen productos nuevos
facturados y excluyen inventario sin ventas y órdenes no facturadas.
Las cantidades se suman desde las líneas de órdenes; el importe usa sus
subtotales guardados, incluso si un producto se vendió con distintos precios.
No se exporta un precio unitario que pueda confundirse con el vigente del catálogo.
Las filas y grupos se ordenan por categoría, subcategoría y nombre.

Los CSV usan UTF-8 con BOM, separador punto y coma y finales CRLF. El módulo
estándar `csv` delimita y escapa comillas, separadores y saltos de línea.
Los nombres que podrían interpretarse como fórmulas se prefijan con apóstrofo
en el CSV; el JSON conserva los textos originales. Los importes mantienen la
unidad entera de la aplicación, sin símbolos ni separadores de miles.

Tras contabilizar el cierre se muestra un formulario con radios: CSV resumen,
CSV detallado, JSON completo y Todo en ZIP. ZIP es la opción inicial y contiene
exactamente los dos CSV y el JSON. «Descargar» obtiene la opción elegida;
«Volver al Dashboard» permite continuar. Registros ofrece el mismo selector
dentro de «Descargar última jornada», un desplegable cerrado en cada visita.
La página inmediatamente posterior al cierre muestra las opciones directamente.
El formulario utiliza HTML y CSS, con etiquetas de al menos 44 px y sin JavaScript.

El endpoint existente `/api/exports/last` admite el parámetro `format` con valores
`json`, `csv_summary`, `csv_detail` o `zip`; por defecto conserva JSON.
`journey_id` vincula la descarga al cierre elegido y rechaza una exportación
reemplazada. El POST de cierre de la API sigue devolviendo JSON.
El cierre de la interfaz redirige al selector mediante GET, para que recargarlo
o repetir descargas no repita la contabilización.

La generación usa `csv`, `io`, `json` y `zipfile` de la biblioteca estándar.
La última exportación se conserva como documento JSON persistente hasta el
siguiente cierre correcto o su recuperación. Los formatos se producen a demanda
desde ese mismo JSON; una nueva jornada activa no modifica la descarga anterior.
En v0.3, el selector incluye el ID de cierre para distinguir nuevos cierres de
una misma jornada. Tras rollback, los archivos requieren cerrar nuevamente la
jornada recuperada; consultar [persistencia y recuperación](../arquitecture/PERSISTENCIA.md).

## Motivos

- El resumen facilita la revisión visual y el detallado ofrece columnas estables.
- Una identidad de tres campos distingue artículos con nombres repetidos.
- Un único cierre de referencia mantiene coherencia entre formatos y estadísticas.
- El ZIP permite una sola descarga y la selección individual evita archivos innecesarios.
- Se conserva el stack y la compatibilidad del endpoint JSON existente.

## Alternativas consideradas

- Solo CSV horizontal: adecuado para lectura, limitado para filtrar y comparar.
- Solo CSV por filas: útil para análisis, sin la presentación resumida solicitada.
- Tres descargas automáticas: impide elegir y puede depender de permisos del navegador.
- Casillas para combinaciones arbitrarias: agrega estados; el ZIP ya reúne todos los formatos.
- XLSX: requiere otro formato y normalmente una dependencia adicional.

## Consecuencias

- Hay tres archivos exportables y un ZIP que los reúne, con nombres ligados al ID.
- El CSV resumido tiene columnas variables; el detallado mantiene cinco columnas.
- El cierre y la descarga son acciones distintas; la interfaz redirige al selector
  mediante GET, sin iniciar una descarga automática.
- Los formatos y el ZIP se construyen en memoria. No constituyen un archivo histórico
  persistente; el supervisor debe conservar las descargas que necesite.
- En programas que no detecten el separador, la importación debe usar punto y coma.

## Revisar cuando

- Se necesiten consultas históricas, persistencia multi-sesión, varias jornadas
  descargables o exportaciones demasiado grandes para memoria.
- Cambien la identidad de los artículos o la unidad monetaria de la aplicación.
- Se acuerde otro formato de planilla o una selección múltiple de archivos.
