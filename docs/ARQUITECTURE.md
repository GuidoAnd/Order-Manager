# Arquitectura de Order Manager — v0.2 en desarrollo

## Propósito

Aplicación web para que un supervisor gestione jornadas, autores, órdenes y ventas. La v0.2 continúa el MVP integrado; v1.0 será la versión final prevista.

## Componentes y datos

El supervisor usa una interfaz HTML/CSS desde el navegador. FastAPI, ejecutado con Uvicorn sobre Python, gestiona la lógica de la aplicación. La jornada activa, sus órdenes, autores, registros y estadísticas se conservan en memoria. Al cerrar la jornada se genera una exportación JSON y se conserva temporalmente la última para permitir otra descarga durante la misma ejecución. Las estadísticas globales y el inventario inicial de artículos se guardan en archivos JSON separados y se recuperan al reiniciar la aplicación.

La aplicación ASGI se define en `order_manager/api.py`. El `api.py` de la raíz
solo expone ese mismo objeto `app` para herramientas que requieren un punto de
entrada en la raíz del repositorio.

## Módulos

- **Jornadas y autores:** creación, consulta, cierre y descarte de jornadas; autores asociados a cada jornada.
- **Órdenes y artículos:** cada orden pertenece a un autor y admite varias líneas de artículos con cantidad y precio unitario. El backend calcula los subtotales y el total. Se pueden consultar, modificar y eliminar órdenes. El catálogo inicial reúne categorías, subcategorías y productos persistentes; el formulario los agrupa para seleccionarlos. Los artículos creados en órdenes se ofrecen temporalmente para nuevas órdenes mientras alguna orden vigente los facture.
- **Artículos vendidos:** la sección Artículos muestra el «Catálogo vendido de la jornada», calculado desde las órdenes actuales y ordenado por unidades vendidas. Los artículos disponibles para nuevas órdenes se administran en una lista separada.
- **Ventas y estadísticas:** las cantidades de las órdenes suman unidades vendidas; el inventario inicial es un catálogo sin existencias físicas. Las órdenes, totales y artículos facturados se muestran por autor, además de los totales de jornada. Los acumulados globales conservan jornadas cerradas, órdenes, unidades e importe, con desglose por artículo y categoría.
- **Registros y exportación:** se registran acciones relevantes del supervisor y se exportan los datos de la jornada en JSON.

## Persistencia del catálogo

`data/inventory.json` se crea con los productos iniciales si aún no existe. Las altas,
ediciones y bajas realizadas en la administración del catálogo se escriben de
forma atómica. Cada jornada toma el catálogo vigente; los cambios de precio
afectan las nuevas líneas de orden, pero las líneas ya guardadas conservan su
precio y total. Un producto sin precio requiere completarlo al facturarlo.
Los artículos creados dentro de órdenes se derivan de las órdenes actuales:
desaparecen de las opciones al borrar o modificar su última orden. Si la
jornada se cierra correctamente, permanecen en el JSON exportado y en los
acumulados globales de ventas.

## Formulario de órdenes

Cada línea permite elegir «Del inventario» o «Nuevo producto» mediante radios.
CSS muestra los campos del modo elegido sin recargar la página. El producto
nuevo tiene nombre y precio propios; su categoría y subcategoría se seleccionan
entre las existentes en el catálogo. CSS muestra únicamente el desplegable de
subcategorías correspondiente a la categoría elegida.

El servidor valida el modo y la relación entre categoría y subcategoría, y utiliza
solo sus campos activos. Una selección previa del inventario no sustituye al
producto nuevo ni le transfiere su precio. Los formularios se validan en el servidor
para evitar que un campo oculto bloquee el envío. Agregar o quitar líneas conserva
los datos del formulario; guardar una orden conserva su copia del precio usado.

En móvil, las acciones finales se apilan y separan. «Guardar orden» ocupa el ancho
disponible y tiene mayor tamaño que «Agregar artículo» (verde) y «Quitar artículo»
(rojo); ambos mantienen una altura mínima de 44 px.

## Órdenes no facturadas

El tipo de orden se selecciona mediante radios «Venta» y «No facturada
(regalo/cancelada)», independiente del origen de cada artículo. La segunda
requiere al menos un artículo y cantidades positivas; oculta los precios y
no aplica los del catálogo. El servidor guarda precios, subtotales y total
como nulos. Las ventas conservan la validación de precios obligatorios.

Las no facturadas aparecen etiquetadas y sin importe en Órdenes y Jornada,
conservan autor, ID, número y artículos, y generan un registro identificable.
El JSON mantiene `status: "not_billed"` y sus líneas. Los resúmenes de ventas,
promedios, catálogo vendido y subtotales por bloques excluyen estas órdenes.
Los artículos que aparezcan solo en ellas no se incorporan como temporales
reutilizables. Cambiar el tipo conserva el ID/número y recalcula los resultados;
convertirla en venta requiere precios válidos.

## Consulta de órdenes

El listado usa una página compartida y mantiene la agrupación por autor.
El tamaño base es 2 hasta 374 px, 3 hasta 650 px, 4 hasta 1023 px y 5 desde
1024 px. Cada página reserva la primera orden pendiente de cada autor y
completa los lugares restantes por número. Si hay más autores pendientes
que lugares, amplía la página para incluir una orden de cada uno.
Anterior y Siguiente recorren todas las órdenes sin duplicarlas.

La búsqueda muestra cinco resultados por página en todos los anchos. Admite
parte del nombre del autor, incluidos nombres numéricos, sin distinguir
mayúsculas ni acentos. Una consulta numérica como 90 también coincide con
la orden de ese número; #90 busca exclusivamente esa orden. Cada orden aparece
una sola vez aunque coincida por ambos criterios.

Una búsqueda nueva comienza en la primera página. El filtro por artículo se
combina con la búsqueda y ambos se conservan al paginar, editar, agregar/quitar
líneas, guardar o eliminar. Las páginas fuera de rango se ajustan a la última
válida. «Acciones» despliega Editar y Eliminar, con colores diferentes.
Los filtros y la paginación no cambian las órdenes ni sus totales.

## Consulta y administración de artículos

La lista de artículos disponibles permite buscar por nombre y filtrar por categoría
y subcategoría. Los resultados por página se adaptan al ancho: dos hasta 374 px,
tres de 375 a 650 px, cuatro de 651 a 1023 px y cinco desde 1024 px. El servidor
prepara esas vistas con la misma búsqueda y paginación; CSS muestra una sola,
sin JavaScript. Las reglas de visibilidad viajan con el HTML para que una hoja
externa antigua no muestre las cuatro vistas. La URL del CSS incluye un hash de
su contenido y cambia al actualizar los estilos. Cada vista permite recorrer
todos los resultados. La búsqueda no distingue mayúsculas ni acentos; sus filtros
se conservan al cambiar de página, editar, guardar o eliminar un artículo del catálogo.

El catálogo vendido se pagina de 2 a 5 filas según el ancho, con
Anterior/Siguiente y fichas en móvil. Su página es independiente de los artículos
disponibles; conserva la búsqueda, filtros y página de ese listado al navegar,
y sus formularios conservan la página del catálogo vendido.

El catálogo vendido muestra nombre, unidades vendidas e importe; la categoría y
subcategoría se conservan en los datos para distinguir productos y contabilizar
sus ventas, aunque no se imprimen junto al nombre.

Agregar y editar artículos usa desplegables de categorías y subcategorías del
catálogo. CSS muestra las subcategorías de la categoría seleccionada; el servidor
valida esa relación e ignora las selecciones de categorías inactivas. Los errores
conservan nombre, precio, selección y búsqueda. Las acciones de Artículos se
centran hasta 650 px, con colores distintos, separación y altura mínima de 44 px.

Los temporales ofrecen «Ver órdenes que lo usan». Esa vista identifica el producto
por categoría, subcategoría y nombre, y permite acceder a las acciones de sus órdenes.
Modificar o eliminar las órdenes recalcula las ventas y la disponibilidad temporal.
Si un enlace ya no corresponde a un producto vigente, la vista informa esa situación.

Hasta 650 px, las tablas de Artículos y el listado de Órdenes se presentan como fichas
verticales con etiquetas. Sus datos y acciones caben sin desplazamiento lateral.
En tamaños mayores conservan la presentación de tabla. Los textos largos pueden
partirse y los campos y columnas flexibles se ajustan al ancho disponible.

## Tablas por autor en Jornada

Cada autor muestra tres tablas: órdenes, subtotales y artículos facturados.
Cada tabla tiene páginas independientes con Anterior/Siguiente y conserva las
páginas de las demás al navegar. Muestra 2 filas hasta 374 px, 3 hasta 650 px,
4 hasta 1023 px y 5 desde 1024 px. Hasta 650 px se presenta como fichas con las
mismas etiquetas; en anchos mayores mantiene la tabla. No requiere desplazamiento
lateral en móvil. Los nombres largos se parten dentro del espacio disponible.

Las órdenes se recorren por número y conservan el acumulado del autor desde
su primera orden, aunque la página actual comience más adelante.
Los artículos se ordenan por unidades vendidas y nombre.

La tabla intermedia agrupa hasta diez órdenes facturadas consecutivas de ese autor,
incluido el último bloque incompleto. Cada fila muestra número de bloque,
cantidad de órdenes y subtotal. «Ver órdenes» despliega los números reales,
por ejemplo #1, #2 y #5. El bloque identifica una agrupación, no un rango de
números generales de jornada. Sus subtotales se recalculan al modificar o
eliminar órdenes.

Las páginas inválidas o fuera de rango se acotan. Un autor sin órdenes muestra
los estados vacíos. La consulta conserva los datos, importes, unidades,
promedios y acumulados completos.

## Nombre de la jornada

La jornada abierta muestra «Editar nombre» junto al título. Un desplegable HTML
contiene el nombre actual y las acciones Guardar y Cancelar. Guardar actualiza
solo el título y registra la acción; conserva identificador, órdenes, autores
y fecha de apertura. Cancelar vuelve a la sección sin modificar datos.
La validación conserva el texto ingresado y mantiene abierto el editor ante
un error. Las jornadas cerradas no pueden renombrarse.

## Gestión de autores

Los nombres registrados permanecen visibles con los formularios cerrados.
«Agregar autor» despliega el campo de nombre, Guardar autor y Cancelar.
«Editar autores» despliega los nombres editables y las acciones Guardar nombre
y Eliminar. El listado de lectura se oculta mientras ese editor está abierto.

Guardar conserva el identificador del autor y sus órdenes; los nombres vacíos
o duplicados se rechazan. Eliminar mantiene la protección existente para autores
con órdenes y no valida el campo de renombrado. Cancelar vuelve a Jornada sin
guardar. Los errores conservan el texto y reabren el formulario correspondiente.

## Navegación y acciones de artículos

Hasta 1023 px, la cabecera muestra «Menú», un desplegable con acceso a las cinco
secciones. Comienza cerrado al cargar cada página y se puede abrir o cerrar con
teclado o toque. Desde 1024 px, los enlaces permanecen visibles en la cabecera.
Ambas presentaciones se generan a partir de una misma lista de secciones; CSS
muestra solo la correspondiente al ancho disponible.

En los artículos del inventario, «Acciones» despliega Editar y Eliminar, con
colores distintos y controles de al menos 44 px. La búsqueda, filtros y página
se conservan al realizar esas acciones. Los artículos temporales mantienen
«Ver órdenes que lo usan» y se administran desde sus órdenes.

## Registros

Los movimientos de la jornada activa se muestran del más reciente al más antiguo,
con 2 a 5 filas por página según el ancho y Anterior/Siguiente. En móvil se presentan
como fichas con Fecha, Acción y Detalle. La paginación no añade eventos ni modifica
su contenido; la exportación incluye todos los registros de la jornada.
El acceso al último JSON permanece separado del listado paginado.

## Cierre y descarte

«Cerrar y contabilizar ventas» prepara la exportación JSON, incorpora la jornada una sola vez a las estadísticas globales y luego permite limpiar sus datos temporales. Si falla la exportación o el guardado, la jornada permanece disponible para reintentar.

El JSON contiene metadatos, autores, órdenes, estadísticas y eventos de la jornada,
además de `new_articles` y `price_changes`. Excluye la copia del inventario inicial
y el contador interno. Cada línea de venta conserva su cantidad, precio y subtotal;
los cambios posteriores de catálogo no modifican esos valores. La actividad de
altas y precios se registra en memoria tras confirmar el guardado y se conserva
si el cierre falla. El [formato de descarga](versions/v0_2.md) detalla los campos.

Tras confirmar el cierre en la interfaz, una página transitoria solicita la descarga de la última exportación y redirige al Dashboard. También ofrece un enlace para repetir la descarga durante la misma ejecución.

«Descartar jornada sin contabilizar ventas» elimina sus datos temporales sin aumentar las estadísticas globales. Ambas acciones requieren confirmaciones claras y diferentes para evitar errores.

## Evolución prevista

El supervisor opera la plataforma sin autenticación. La autenticación y la persistencia de permisos se abordarán en una actualización menor posterior. CSV sigue previsto para v0.2; MariaDB se evaluará después de v1.0.

## Decisiones técnicas

- [FastAPI como servidor](decisions/ADR-001-FastApi.md).
- [Persistencia local en JSON](decisions/ADR-002-Json-persistance.md).
- [Exportación CSV prevista](decisions/ADR-003-csv-export.md).
- [Pruebas funcionales en móviles](decisions/ADR-004-mobile-testing.md).
