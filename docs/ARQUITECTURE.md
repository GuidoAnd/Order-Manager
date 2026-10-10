# Arquitectura de Order Manager — v0.3 en desarrollo

## Propósito

Aplicación web para que un supervisor gestione jornadas, autores, órdenes y ventas.
La v0.3 comienza con persistencia recuperable; v1.0 será el MVP final previsto.
El [resumen de v0.3](version/v0_3.md) distingue lo implementado de lo pendiente.
La validación histórica de v0.2 permanece en sus informes de versión.

## Componentes y datos

Navegador → HTML/CSS → FastAPI/Uvicorn → Store → revisiones JSON bajo `DATA_DIR`.
La jornada, el catálogo, los acumulados, el snapshot previo al último cierre y
la última exportación se confirman como un conjunto coherente por acción válida.
La memoria sirve para trabajar; al reiniciar se carga la revisión confirmada.
`persistence.py` coordina archivos y manifiestos; `state_validation.py` valida
integridad de negocio y relaciones. `Store` conserva la lógica de órdenes y jornadas.
Consultar [persistencia y recuperación](PERSISTENCIA.md) para formato y operación.
`runtime_logging.py` configura diagnóstico por instancia, JSON UTC, consola y
archivo rotado; captura errores de acciones, exportación y solicitudes. DEBUG
agrega fases y tiempos sin datos de formularios. El historial de acciones
permanece separado e íntegro; consultar [logging](LOGGING.md).

La aplicación ASGI se define en `order_manager/api.py`. El `api.py` de la raíz
solo expone ese mismo objeto `app` para herramientas que requieren un punto de
entrada en la raíz del repositorio.

## Módulos

- **Jornadas y autores:** creación, consulta, cierre y descarte de jornadas; autores asociados a cada jornada.
- **Órdenes y artículos:** cada orden pertenece a un autor y admite varias líneas de artículos con cantidad y precio unitario. El backend calcula los subtotales y el total. Se pueden consultar, modificar y eliminar órdenes. El catálogo inicial reúne categorías, subcategorías y productos persistentes; el formulario los agrupa para seleccionarlos. Los artículos creados en operaciones válidas se incorporan al catálogo persistente, aunque después se elimine su orden.
- **Artículos vendidos:** la sección Artículos muestra el «Catálogo vendido de la jornada», calculado desde las órdenes actuales y ordenado por unidades vendidas. Los artículos disponibles para nuevas órdenes se administran en una lista separada.
- **Ventas y estadísticas:** las cantidades de las órdenes suman unidades vendidas; el inventario inicial es un catálogo sin existencias físicas. Las órdenes, totales y artículos facturados se muestran por autor, además de los totales de jornada. Los acumulados globales conservan jornadas cerradas, órdenes, unidades e importe, con desglose por artículo y categoría.
- **Registros y exportación:** se registran acciones relevantes del supervisor y se exporta la jornada en JSON y dos CSV, individualmente o juntos en ZIP.

## Persistencia del catálogo

El catálogo vive en `inventory.json` dentro de la revisión referenciada por
`current.json`. Una instalación nueva usa el catálogo inicial; la migración
valida y conserva los JSON originales. Altas, ediciones y bajas se confirman
junto con el estado de jornada. Las nuevas líneas usan el catálogo vigente,
mientras las líneas guardadas conservan sus precios y totales. Los artículos
creados en órdenes se guardan tras validar la operación completa y permanecen
al eliminar sus órdenes o descartar la jornada.

Las altas y ediciones del catálogo reutilizan la escritura de categorías y
subcategorías existentes cuando los nombres solo difieren en mayúsculas.
Esto mantiene coherentes los artículos, los filtros y los desplegables.

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

Al editar una orden, los desplegables también admiten las categorías y
subcategorías originales de sus líneas, aunque hayan llegado por la API y no
pertenezcan al catálogo inicial. Estas opciones se agregan a una copia para ese
editor; las altas válidas de artículos por API también conservan su taxonomía en el inventario. Las altas desde el formulario
siguen usando las categorías disponibles del catálogo.

Las cantidades y precios rechazan booleanos y tienen un máximo técnico común
de `9223372036854775807` por campo (`2^63 - 1`). Se valida antes de guardar,
tanto en la API como en la lógica usada por los formularios. Se conservan las
cantidades positivas, los precios naturales y los precios nulos donde están
permitidos. Este límite evita que una entrada extrema impida calcular promedios
o cerrar la jornada; los subtotales y totales siguen calculándose con enteros.

Al guardar una orden se obtiene una sola vez el catálogo disponible, únicamente
si alguna línea lo usa. La consulta se reutiliza por identificador durante esa
operación, bajo el bloqueo de la jornada; se reconstruye en el siguiente guardado
para respetar cambios de catálogo en operaciones posteriores. Al editar una línea
guardada se conserva su precio salvo modificación explícita.

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
Sus artículos nuevos también se incorporan al catálogo persistente, con precio
opcional, sin aumentar las ventas. Cambiar el tipo conserva el ID/número y recalcula los resultados;
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

La búsqueda filtra y ordena una vez por petición; las cuatro presentaciones
responsive paginan esos mismos resultados. No se conserva una caché entre
peticiones y se mantiene la interfaz de consulta `ArticleSearch.results`.

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

Los artículos del catálogo ofrecen «Ver órdenes que lo usan». Esa vista identifica el producto
por categoría, subcategoría y nombre, y permite acceder a las acciones de sus órdenes.
Modificar o eliminar las órdenes recalcula las ventas y conserva los artículos del catálogo.
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

El formulario incluye el identificador de la jornada mostrada. Al guardar se
comprueba ese identificador bajo el mismo bloqueo que protege el renombrado;
un formulario de otra jornada o sin identificador devuelve `409` y conserva
el nombre, los eventos y los demás datos de la jornada actual.

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
se conservan al realizar esas acciones. «Ver órdenes que lo usan» permite
consultar las órdenes correspondientes sin alterar el artículo.

## Registros

Los movimientos confirmados de todas las jornadas se muestran del más reciente al más antiguo,
con 2 a 5 filas por página según el ancho y Anterior/Siguiente. En móvil se presentan
como fichas con Fecha, Acción y Detalle. La paginación no añade eventos ni modifica
su contenido; cada exportación incluye los registros propios de esa jornada.
El selector de descarga de la última jornada cerrada permanece separado del listado paginado.
En Registros se presenta dentro de «Descargar última jornada», un desplegable
cerrado por defecto. Se abre o cierra con toque o teclado, sin afectar los archivos.

## Cierre y descarte

«Cerrar y contabilizar ventas» publica juntos exportación, acumulados, snapshot
previo y ausencia de jornada activa. Un fallo antes de publicar conserva la
jornada; un resultado incierto después de publicar bloquea operaciones hasta verificarlo.

El JSON contiene metadatos, autores, órdenes, estadísticas y eventos de la jornada,
además de `new_articles` y `price_changes`. Excluye la copia del inventario inicial
y el contador interno. Cada línea de venta conserva su cantidad, precio y subtotal;
los cambios posteriores de catálogo no modifican esos valores. La actividad de
altas y precios se conserva en las revisiones persistentes, incluso si el cierre falla. El [formato de descarga](version/v0_2.md#json-descargado) detalla los campos.

Tras confirmar el cierre, la interfaz redirige mediante GET a un selector con
radios: CSV resumen, CSV detallado, JSON completo y Todo en ZIP. El usuario
descarga la opción elegida y puede volver al Dashboard. No hay descarga automática. Registros ofrece el mismo selector. Recargar esa página
o repetir la descarga no vuelve a contabilizar ventas.

`order_manager/export_formats.py` construye los formatos a demanda desde el JSON
del cierre, sin consultar la jornada activa ni alterar los acumulados. El resumen
presenta nombres y unidades en dos filas por categoría; el detallado tiene columnas
estables de categoría, subcategoría, artículo, unidades e importe. Los dos agregan
las ventas de todos los autores y excluyen órdenes no facturadas y productos sin
ventas. Las líneas guardadas determinan las cantidades y los importes.

Los CSV usan UTF-8 con BOM, punto y coma y CRLF. El ZIP contiene exactamente
los dos CSV y el JSON. Se generan con la biblioteca estándar de Python.
`/api/exports/last` mantiene JSON por defecto y acepta `format` para los demás
formatos. El ID de jornada impide entregar otra exportación cuando la anterior
fue reemplazada. La última descarga se conserva hasta el siguiente cierre
correcto o su recuperación, incluso tras reiniciar. `close_id` distingue cierres
diferentes de una misma jornada; el selector incluye ese ID. Se conserva solo
la última exportación, sin un archivo consultable de todas las descargas.

«Descartar jornada sin contabilizar ventas» confirma la ausencia de jornada activa
sin aumentar acumulados y conserva sus altas de inventario y eventos.

«Recuperar última jornada» abre una advertencia con el cierre objetivo y la jornada
actual que se descartará. El servidor valida ID de cierre, revisión y jornada
confirmados. El rollback restaura el estado previo al cierre y sus acumulados,
conserva el catálogo vigente y consume la recuperación. Las órdenes vuelven a ser
editables; el siguiente cierre genera snapshot y archivos nuevos y contabiliza
una vez. El historial conserva cierres, descartes y recuperación. Mientras la
jornada recuperada esté abierta, el selector informa que requiere otro cierre.

## Evolución prevista

El supervisor opera la plataforma sin autenticación. La autenticación y la persistencia de permisos se abordarán en una actualización menor posterior. MariaDB se evaluará después de v1.0.

Jinja2 queda pendiente dentro de v0.3. Actualmente el HTML se construye desde Python y
la presentación adaptable usa CSS y controles nativos de HTML.

## Límites de ejecución

El estado de trabajo y el bloqueo `RLock` pertenecen a un único proceso. La
aplicación requiere una sola instancia y un solo worker; varias instancias o
workers no compartirían la jornada ni coordinarían las escrituras locales.
La ruta `DATA_DIR` necesita permisos de escritura. Reiniciar restaura la última
revisión confirmada, incluida jornada y descarga. Compartir un volumen no habilita
múltiples escritores. Los fallos físicos requieren copias de seguridad externas.

Los archivos descargados contienen una jornada completa. La aplicación conserva
la última exportación y el snapshot recuperable; no ofrece un archivo histórico
consultable de todas las órdenes ni descargas. Los
acumulados globales son resúmenes de ventas. La validación de navegador usa
Chromium emulado desde 320 px; no acredita dispositivos físicos ni otros motores.

## Decisiones técnicas

- [FastAPI como servidor](decisions/ADR-001-FastApi.md).
- [Persistencia local en JSON](decisions/ADR-002-Json-persistance.md).
- [Exportación CSV y selección de descargas](decisions/ADR-003-csv-export.md).
- [Pruebas funcionales en móviles](decisions/ADR-004-mobile-testing.md).
