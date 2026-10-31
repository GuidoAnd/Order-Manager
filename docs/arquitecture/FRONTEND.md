# Interfaz y plantillas de v0.3.1

## Presentación

HTML/CSS y Jinja2, sin JavaScript. `templating.py` configura escape automático,
`StrictUndefined` y hasta 128 plantillas compiladas. Los datos de negocio se
preparan por petición; las plantillas se distribuyen en `order_manager/templates`.
`safe` se reserva para fragmentos internos cuyos datos ya están escapados.

## Editor y selección de artículos

| Ruta | Uso |
| --- | --- |
| `/ordenes` | Listado, Buscador de Órdenes y Agregar nueva orden. |
| `/ordenes/nueva` | Abrir un borrador de creación. |
| `/ordenes/{id}/editar` | Abrir un borrador de edición. |
| `/ordenes/borrador/{token}` | Consultar una versión del borrador mediante GET. |
| `/ui/orders/form` | Guardar o procesar acciones del editor mediante POST → 303 → GET. |
| `/ordenes/borrador/{token}/articulos` | Consultar el selector de artículos. |
| `/ui/orders/articles` | Procesar selección, cantidades y filtros del selector. |

Agregar/quitar líneas y corregir errores conservan los campos en un borrador,
sin modificar órdenes confirmadas, catálogo ni revisiones. Cancelar vuelve al
listado conservando búsqueda, filtro y página; guardar conserva ese mismo
contexto. Un guardado exitoso consume la sesión de edición: reenviar la misma
operación devuelve su resultado, sin crear otra orden. Abrir otra sesión permite
crear una orden distinta aunque su numeración y contenido coincidan.

Antes de editar se compara la orden vigente con la capturada al abrir el editor.
Si cambió o se eliminó, se rechaza la sobrescritura con 409 y se conserva el
borrador. También se comprueba la jornada y, para altas o cambios de autor, la
tanda esperada. Estas protecciones del editor HTML no constituyen control de
versiones para todos los clientes de la API ni autenticación.

Los borradores viven en memoria de la única instancia, con tokens aleatorios,
30 minutos desde la apertura, hasta 128 entradas y 8 MiB de contenido serializado
estimado. Caducidad, expulsión o reinicio requieren abrir otro editor; no pierden
órdenes ya confirmadas. Los borradores no se guardan en DATA_DIR. Tras un reinicio
puede rechazarse antes un token CSRF anterior con 403. El flujo GET evita depender
de recuperar un POST del editor desde el historial; no garantiza el comportamiento
de todos los navegadores.

El selector permite buscar por nombre sin distinguir acentos/mayúsculas y filtrar
por categoría/subcategoría. La selección múltiple usa casillas y cantidades;
conserva las selecciones enviadas al cambiar de página o filtro. Aplicarlas las
agrega juntas al borrador, hasta 50 líneas. Buscar/Cambiar artículo de una línea
solo modifica esa línea. Cancelar la selección conserva el editor anterior.
Los cambios se envían al servidor mediante formularios; no hay actualización
instantánea en el cliente.

Cada línea distingue inventario y producto nuevo. El servidor ignora los campos
inactivos y valida categoría/subcategoría. Los artículos sin precio requieren uno
al facturarse. La edición conserva la referencia y el precio ya guardados; cambiar
la referencia permite usar el precio del nuevo artículo. Un artículo retirado del
catálogo sigue disponible en su orden. Las categorías válidas de la API se
registran con las altas de catálogo.

## Series, tandas e identidad

| Serie | Numeración inclusiva |
| --- | --- |
| 10 | 001–080 |
| 20 | 081–160 |

En Jornada → Autores, el panel Asignar serie y tanda permite asignar una de las
dos series a cada autor. La tanda se numera automáticamente desde 1 por autor y
jornada. Solo puede haber una abierta; cerrarla exige confirmación. Luego puede
asignarse la misma serie o la otra en una tanda nueva. El panel conserva su página
al asignar, cerrar, cancelar o presentar un error.

La orden pide autor y numeración manual, sin selector de serie. Toma la asignación
capturada al abrir el editor y valida el rango. Si esa tanda se cerró o cambió,
rechaza una alta obsoleta conservando el borrador. Los números pueden repetirse;
se guardan como enteros y se muestran con tres dígitos. No se proponen ni se
incrementan automáticamente. El UUID y el contador cronológico son automáticos.

Las correcciones dentro de la jornada abierta conservan la tanda original aunque
esté cerrada y haya otra activa. Cambiar de autor requiere la asignación válida
del destino. Las órdenes anteriores sin tanda conservan esa condición; si tampoco
tenían serie, una corrección determina la serie mediante su numeración válida.
Cerrar la jornada cierra sus tandas abiertas; el rollback recupera el estado exacto
previo, incluidas las tandas que estaban abiertas.

POST/PUT de órdenes requiere `serial_number`, autor y líneas. `series` es opcional
cuando existe una asignación; si se envía debe coincidir. Para una nueva orden se
puede enviar `batch_id` esperado para detectar una tanda cerrada o reemplazada:

```json
{
  "author_id": "ID_DEL_AUTOR",
  "batch_id": "ID_DE_LA_TANDA_ABIERTA",
  "serial_number": 81,
  "status": "sale",
  "lines": [{"catalog_id": "ID_DEL_ARTICULO", "quantity": 1}]
}
```

Se conserva el contrato anterior con serie explícita para autores que aún no usan
tandas. Una vez que un autor las usa, las altas numeradas requieren una activa.
Actualizar una orden del mismo autor conserva su tanda original; `batch_id` no
permite trasladarla a otra tanda del mismo autor. La numeración debe corresponder
a su serie. No hay rutas JSON de administración de tandas; se gestionan desde
Jornada. Las entradas internas antiguas del Store sin numeración se mantienen por
compatibilidad; el editor y la API requieren numeración.

Cada línea nueva recibe `line_id`. Devolverlo en PUT conserva su identidad al
reordenar referencias repetidas o quitar otras líneas; duplicados e identificadores
ajenos se rechazan. Sin ID se conserva la correspondencia posicional anterior.
Los formularios transportan referencias estables y las confirman al guardar.
Los campos de serie, numeración y tanda persisten y se incluyen en JSON; los CSV
agregados mantienen su contrato. El JSON conserva `export_format: "v0.2"`.

## Ventas y no facturadas

Una orden contiene de 1 a 50 líneas con cantidades positivas. Una venta exige
precios naturales; los subtotales y el total se calculan con enteros. Cantidad y
precio tienen un máximo de `9223372036854775807` y rechazan booleanos.

No facturada (regalo/cancelada) exige artículos y cantidades, pero guarda precios,
subtotales y total nulos. No aporta ventas, unidades ni promedios. Figura en los
bloques de diez registros con aporte cero. Cambiar el tipo conserva ID y número;
volver a venta exige precios válidos. Sus artículos nuevos se incorporan al catálogo.
Las líneas históricas conservan precios frente a cambios posteriores del catálogo.

## Búsquedas y paginación

El tamaño habitual es 2 filas hasta 374 px, 3 hasta 650 px, 4 hasta 1023 px y
5 desde 1024 px. CSS muestra una sola vista. Hasta 650 px, los listados se
presentan como fichas con etiquetas. Los filtros y las páginas afectan la
presentación, no los cálculos completos.

- **Órdenes:** el listado sin búsqueda distribuye órdenes entre autores y ordena
  por contador cronológico. El único Buscador de Órdenes ofrece Todos, Autor, ID
  y Numeración. Autor admite coincidencia parcial sin acentos/mayúsculas; ID
  busca contador exacto, con `#` opcional, o UUID completo; Numeración busca el
  número manual exacto y devuelve todas sus repeticiones. Todos combina las
  búsquedas anteriores. Se combina con el filtro de identidad de artículo.
  Editar, cancelar, borrar, elegir artículos y corregir errores conservan contexto.
  Una edición conserva ID, contador y posición; cambiar un campo filtrado puede
  sacar la orden de ese resultado sin eliminarla.
- **Artículos:** búsqueda por nombre y filtros de categoría/subcategoría. Filtra
  y ordena una vez por petición para las cuatro vistas. Altas y ediciones usan
  desplegables validados; un enlace de edición inexistente devuelve 404.
- **Catálogo vendido:** orden por unidades descendentes y nombre; muestra unidades
  e importe. Su página es independiente del inventario y conserva sus filtros.
- **Registros:** historial del más reciente al más antiguo, con fecha, acción y
  detalle. Consultarlo no genera eventos ni modifica descargas.

Las páginas fuera de rango se ajustan. La URL del CSS incluye un hash para evitar
vistas duplicadas por una hoja antigua.

## Jornada y subtotales

Cada autor tiene tablas independientes de órdenes, bloques y artículos facturados.
Los acumulados se calculan antes de paginar. Los bloques contienen hasta diez
órdenes existentes de una misma tanda, ordenadas por numeración y contador como
desempate. No reservan espacios para números ausentes. Una tanda repetida tiene
bloques separados, titulados «Bloque N de la tanda M». Las órdenes antiguas se
agrupan como «Bloque N sin tanda asignada». Cada fila incluye cantidad, subtotal
y detalle; los regalos cuentan como registros y aportan cero. Corregir o borrar
recalcula los bloques; no cambia los acumulados facturados de forma independiente.

Los enlaces de resultados conservan las otras páginas y omiten valores iguales
a 1. Consultas mayores de 4096 caracteres usan un token por instancia asociado a
la jornada: 30 minutos, máximo 64 entradas y 32768 selecciones totales. Se expulsan
los menos recientemente consultados; un estado individual excesivo devuelve 413.
Un enlace perdido muestra aviso y restablece páginas. Solo contiene navegación,
sin escrituras de negocio en DATA_DIR.

Editar nombre cambia solo el título de la jornada abierta y comprueba su ID.
Los autores se administran mediante Agregar autor y Editar autores. Renombrar
conserva IDs y órdenes; no se admite borrar autores con órdenes.

Finalizar jornada está antes de Autores y Resultados, alineado a la derecha en
escritorio y centrado en móvil. Cierre, descarte y recuperación usan confirmación;
consultar [persistencia](PERSISTENCIA.md). Después del cierre se elige JSON, CSV
resumen, CSV detallado o ZIP; Registros ofrece el mismo selector, cerrado por
defecto. Las descargas son directas y su recepción la gestiona el navegador.
Repetirlas no contabiliza ventas.

## Avisos y accesibilidad

Las operaciones confirmadas muestran un aviso con referencias de orden, autor,
artículo, jornada o tanda según la acción. Los errores permanecen visibles;
los avisos de éxito se ocultan mediante CSS a los ocho segundos, sin botón de
ocultar. Su token aleatorio está asociado al destino, dura cinco minutos y admite
hasta 256 entradas por instancia. Reiniciar pierde esos avisos, sin afectar datos.
No se informa que una descarga terminó de guardarse en el dispositivo.

Hasta 1023 px, Menú despliega las secciones; desde 1024 px, los enlaces permanecen
visibles. `details`/`summary` admite toque y teclado. Acciones próximas usan colores
diferentes y controles de al menos 44 px. Guardar/Cancelar se separan de Agregar
artículo. El panel de asignación se centra en móvil y usa tabla en escritorio.

Los flujos se validan en 320×568, 375×667, 430×932, 768×1024 y 1366×768.
[Seguridad](SEGURIDAD.md) describe la protección HTTP y
[ADR-006](../decisions/ADR-006-jinja2-e-interfaces-de-ordenes.md) registra decisiones
y límites del editor.
