# Auditoría de errores y optimización — v0.2

Creación UTC: **2026-10-02T05:23:23Z**.
Actualización UTC: **2026-10-02T05:40:05Z**.
Revisión documental UTC: **2026-10-02T13:37:19Z**; comando portable sin rutas
del entorno privado. Se conservan los resultados y mediciones originales.
Versión: **v0.2 en desarrollo**. Resultado final: **PASS**.

## Alcance e intervenciones

La primera intervención corrigió el punto 3. Tras la autorización posterior del
usuario, se corrigieron los puntos 1, 2, 4, 5 y 6 en el mismo repositorio y se
amplió esta auditoría. Se conservaron los cambios previamente pendientes.

Se revisaron las instrucciones, la arquitectura y las pruebas; se reprodujeron
los fallos con datos temporales, se aplicaron correcciones acotadas y se midió
el rendimiento antes y después sobre un conjunto sintético común.

## 1. Renombrado desde un formulario de otra jornada

**Error:** abrir el editor de nombre de una jornada, cerrarla o descartarla desde
otra pestaña y crear una nueva permitía que el formulario antiguo renombrara
la jornada nueva.

**Corrección:** el editor envía `journey_id`; `Store.rename_journey` comprueba el
identificador dentro del mismo bloqueo que protege la modificación. Un formulario
con identificador antiguo o ausente devuelve `409` sin alterar nombre, eventos
ni otros datos. El cierre y descarte mantienen su protección anterior.

La firma del método conserva un identificador esperado opcional para sus llamadas
existentes. El requisito del identificador se aplica al formulario de renombrado;
el contrato de la ruta JSON que opera sobre la jornada actual se conserva.

**Pruebas:** cierre y descarte, identificador ausente y antiguo, conservación de
datos y guardado posterior con el identificador correcto. Las pruebas del editor
ahora envían el campo oculto que incluye el formulario real.

## 2. Coherencia de categorías entre API y formularios

**Errores:** el catálogo aceptaba `cafetería / infusiones` pero los desplegables
contenían `Cafetería / Infusiones`; una orden creada por la API con una categoría
o subcategoría propia tampoco podía conservarla al editarse desde el navegador.

**Corrección:** las altas y ediciones de artículos reutilizan los nombres de los
grupos existentes cuando coinciden sin distinguir mayúsculas. No se duplican
grupos por diferencias de escritura. El guardado sigue siendo atómico.

Al editar una orden, `get_order_inventory` agrega sus grupos originales a una
copia de las opciones del catálogo. El renderizado y la validación del formulario
usan esa misma regla. La selección reconoce diferencias de mayúsculas, y las
categorías temporales no se escriben al inventario. Los formularios de alta siguen
usando las opciones del catálogo. Se conserva la capacidad previa de la API para
recibir categorías propias, sin rechazar órdenes antes válidas.

**Pruebas:** altas y ediciones del catálogo por API, persistencia y selección
correcta; categorías y subcategorías propias de órdenes de venta y no facturadas;
edición posterior desde el formulario, conservación de ID/número y ausencia de
escrituras al inventario.

## 3. Booleanos usados como cantidades y precios

**Error:** Pydantic convertía `true` en `1` y `false` en `0` antes de las
comprobaciones de `Store`. Una venta con `quantity: true` y `unit_price: false`
podía guardarse como una unidad a precio cero.

**Corrección previa conservada:** `NonBooleanInt` usa `BeforeValidator` para
rechazar booleanos antes de convertirlos en `ArticleInput.unit_price`,
`LineInput.unit_price` y `LineInput.quantity`. La respuesta es `422`, sin guardar
cambios. Se mantienen las conversiones numéricas previas, como `"2"` y `2.0`,
y los precios nulos donde corresponden; no se sustituyeron por enteros estrictos.

**Pruebas:** 25 regresiones de creación y edición, ambos booleanos, tipos de orden,
conservación de datos y entradas numéricas u opcionales válidas. Antes de la
corrección se obtuvo un fallo esperado: `201` en lugar de `422`.

## 4. Números extremos que impedían estadísticas y cierre

**Error:** un precio de 401 dígitos se guardaba, pero el cálculo del promedio
producía `OverflowError`. Fallaban Dashboard, Jornada, Artículos, estadísticas
y cierre. Una cadena de miles de dígitos también podía superar el límite de
conversión de enteros de Python sin una respuesta de validación adecuada.

**Corrección:** cantidades y precios tienen un máximo técnico común de
`9223372036854775807` (`2^63 - 1`), definido por `MAX_INPUT_INTEGER`.
Pydantic aplica ese máximo a la API y `bounded_integer` lo aplica a la lógica
usada por formularios y guardados directos. Los errores de conversión se traducen
a validación. También se comprueban los precios tomados del catálogo al vender.

Se eligió un límite de entero de 64 bits por campo, sin cambiar la moneda ni
las fórmulas. Incluso una orden de 50 líneas con cantidad y precio máximos tiene
un promedio finito. Los subtotales y totales siguen siendo enteros de Python;
no se convierten a flotante ni se limitan al máximo de un campo individual.

**Pruebas:** máximo más uno, valor de 401 dígitos y cadena de 5.000 dígitos, en
altas y ediciones por API y formularios. Se comprueba que no haya cambios en
órdenes o inventario, que las páginas y el cierre sigan disponibles, y que el
máximo permitido funcione en una orden de 50 líneas.

## 5. Reconstrucción repetida del catálogo al guardar una orden

**Problema:** cada línea del inventario reconstruía y copiaba el catálogo,
recorriendo todas las órdenes para derivar los artículos temporales.

**Optimización:** se construye un mapa de artículos por ID al necesitar la primera
línea del catálogo, y se reutiliza durante ese guardado bajo el bloqueo existente.
Las órdenes con artículos nuevos no necesitan esa consulta. No se conserva el
mapa entre operaciones, por lo que los precios y temporales se actualizan al
siguiente guardado.

**Pruebas:** órdenes de 50 líneas con artículos persistentes y temporales,
edición después de un cambio de precio y rechazo de un temporal que desapareció
tras eliminar su última orden. Un rechazo conserva los datos y contadores.

## 6. Filtrado y ordenamiento repetidos en las vistas responsive

**Problema:** el catálogo completo se filtraba y ordenaba cuatro veces por
petición, una por tamaño de página.

**Optimización:** `ArticleSearch.matching` calcula las coincidencias ordenadas
una vez; `paginate` divide esos resultados para los tamaños 5, 4, 3 y 2.
`ArticleSearch.results` conserva su interfaz para los consumidores existentes.
Cada petición vuelve a consultar los datos actuales.

**Pruebas:** una sola búsqueda por petición, disponibilidad de artículos nuevos
en la siguiente consulta y conservación de filtros, límites y navegación. El
HTML del catálogo fue idéntico antes y después sobre el conjunto de referencia.

## Medición de rendimiento

Conjunto: 1.000 órdenes con productos temporales y una orden de prueba de 50
líneas. Se usó el mismo contenido en memoria antes y después; los tiempos son
medianas de tres ejecuciones locales y no representan una garantía en producción.

| Operación | Antes | Después |
| --- | --- | --- |
| Consultas del catálogo por guardado de 50 líneas | 50 | 1 |
| Tiempo de guardado de esa orden | 1,5337 s | 0,0306 s |
| Filtrados y ordenamientos por página de artículos | 4 | 1 |
| Tiempo de generación de la página de artículos | 0,1279 s | 0,0866 s |
| HTML de artículos con el mismo conjunto | Referencia | Idéntico |

## Validación

| Ejecución | Resultado |
| --- | --- |
| Regresión inicial del punto 3, antes de corregir | 1 FAIL esperado, 0,87 s |
| Validación de la primera intervención | 98 PASS, 3,89 s |
| Regresiones existentes afectadas por los puntos restantes | 86 PASS, 3,91 s |
| Nuevas regresiones de los puntos 1, 2, 4, 5 y 6 | 51 PASS, 2,97 s |
| Suite completa con navegador | 285 PASS, 214,68 s |
| Desglose de la suite completa | 215 unitarias/integrales y 70 de navegador |
| Formato del diff y archivos nuevos | PASS |

La suite completa utiliza pytest y Chromium con Playwright en 320x568, 375x667,
430x932, 768x1024 y 1366x768. Las nuevas comprobaciones de navegador recorren la
edición de categorías originales, agregar/quitar líneas, errores de cantidad,
reintento de guardado y renombrado con un formulario antiguo, sin desborde.

Comando de validación completa con las dependencias de desarrollo y Chromium
de Playwright ya instalados y configurados en el entorno:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider --tb=short --maxfail=3
```

Las pruebas y mediciones usan datos temporales y no abren puertos de red.
Chromium emulado no sustituye pruebas en dispositivos físicos u otros motores.

## Comportamiento conservado y documentación

- Las ventas a precio numérico cero siguen siendo válidas.
- Las órdenes regalo/canceladas conservan `status: "not_billed"`, importes nulos
  y registros identificables. Siguen excluidas de ventas, unidades, promedios y
  CSV, y presentes en el JSON. No se cambiaron los formatos de exportación.
- Se mantienen el stack, las dependencias, la estructura de directorios y v0.2.
- Se actualizó `docs/ARQUITECTURE.md` con la protección del renombrado, las
  categorías originales, el límite técnico y el alcance de las consultas
  reutilizadas. No se incorporó una caché persistente ni una nueva tecnología.
