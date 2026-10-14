# ADR-006 — Plantillas Jinja2 e interfaces de órdenes

## Estado

Aceptada.

## Fecha

2026-10-14

## Contexto

El HTML del MVP se construía en funciones Python junto con la preparación de
listas, filtros y formularios. La pantalla de Órdenes incluía tanto el listado
como el formulario de creación o edición. Este acoplamiento dificultaba modificar
la presentación y generaba el editor durante consultas del listado.

Se requiere separar la presentación, ofrecer pantallas dedicadas a crear y editar,
y registrar una identificación manual de órdenes mediante dos series fijas.
Deben conservarse la persistencia por acción, el rollback, las exportaciones,
las restricciones de seguridad y el uso móvil desde 320 px.

## Decisión

Usar Jinja2 3.1.6 y MarkupSafe 3.0.3 como dependencias de ejecución fijadas,
compatibles con Python 3.13. Mantener las demás versiones del proyecto.

- Guardar las pantallas y los componentes HTML en `order_manager/templates`.
  Preparar contextos y aplicar reglas de negocio en Python. Las plantillas no
  reciben el almacenamiento ni ejecutan operaciones de negocio.
- Compartir la estructura de página, navegación, métricas, campos ocultos y
  opciones mediante plantillas y macros. Mantener pequeños ayudantes de
  composición para las vistas adaptables existentes.
- Configurar un único `Environment`, escape automático HTML y `StrictUndefined`.
  Reutilizar hasta 128 plantillas compiladas y comprobar cambios de sus archivos.
  Esta caché almacena plantillas, no jornadas, consultas ni datos de formularios.
- Reservar `safe` para fragmentos HTML construidos por componentes internos que
  escapan sus datos. Conservar el token de formulario, CSP y controles HTTP.
- Usar `/ordenes` para el listado, `/ordenes/nueva` para creación y
  `/ordenes/{id}/editar` para edición. Compartir el guardado en
  `/ui/orders/form`. La ruta antigua con `edit` redirige al editor dedicado.
- Mostrar Agregar nueva orden antes del listado y Editar orden en sus acciones.
  Cancelar vuelve al Dashboard sin guardar. Tras guardar, conservar filtros,
  búsquedas y página del listado. Las acciones de agregar o quitar líneas y los
  errores conservan autor, artículos, serie, número y contexto de navegación.
- Elegir manualmente serie 10 o 20; admitir respectivamente números 001–080
  y 081–160, inclusivos. Permitir repeticiones, incluso para el mismo autor.
  No crear otras series, proponer números ni incrementarlos automáticamente.
- Mantener el ID automático y el contador cronológico interno. Guardar `series`
  y `serial_number` como campos separados y conservar el ID al editar. La API
  de creación y actualización exige esos campos; el servidor valida el rango.
- Mostrar la identificación manual en Órdenes y Jornada, con tres dígitos.
  La búsqueda numérica admite numeración manual; `#n` conserva la consulta por
  contador interno. Los resultados pueden incluir órdenes con números repetidos.
- Guardar los campos en las revisiones, snapshot y JSON de cierre. Mantener
  legibles las órdenes históricas sin serie, sin asignarles valores automáticamente.
  El JSON conserva `export_format: v0.2` y añade campos en las órdenes asignadas.
  Los CSV de ventas agregadas conservan su contrato.
- Ubicar la finalización debajo del bloque principal de Jornada y retirar el
  acceso Ver órdenes que lo usan de Artículos. Conservar filtros y paginación.
- Asociar los errores de serie y numeración a sus campos y conservar los valores
  introducidos, además del aviso general del formulario.

## Motivos

- Las plantillas permiten revisar y modificar pantallas sin mezclar su estructura
  con cálculos, filtrado o escrituras persistentes.
- Los componentes compartidos reducen duplicación de presentación y mantienen
  reglas uniformes de escape.
- Las pantallas dedicadas reducen elementos ajenos a la tarea de carga o edición.
- La consulta del listado evita construir campos y opciones del editor.
- Separar identificación manual y contador interno permite repeticiones sin
  alterar orden cronológico, cálculos ni referencias históricas.

## Alternativas consideradas

- Conservar toda la presentación en cadenas Python: mantiene el acoplamiento
  y dificulta revisar cambios de interfaz.
- Incorporar un frontend JavaScript: añade una tecnología fuera del alcance
  actual; HTML, CSS y renderizado del servidor cubren los flujos requeridos.
- Reemplazar el contador interno por la numeración manual: las repeticiones
  impedirían usarlo como referencia cronológica única.
- Numerar automáticamente: contradice la asignación manual acordada.

## Consecuencias

- Jinja2 y MarkupSafe son dependencias runtime; pytest y Playwright siguen
  separados en los requisitos de test y desarrollo.
- Los archivos de plantillas deben distribuirse junto con la aplicación.
- El escape automático no elimina la revisión de fragmentos marcados como seguros.
- Los clientes de creación y actualización de órdenes deben enviar la serie y
  numeración; las lecturas históricas pueden carecer de esos campos.
- Las series permanecen fijas y no constituyen un identificador único.
- Se mantiene una instancia y un worker. Esta decisión no modifica el modelo
  de concurrencia, autenticación ni despliegue.
- La reutilización de plantillas y la separación del editor reducen trabajo
  repetido; no se establece una mejora porcentual ni una garantía de latencia.
  La validación funcional no sustituye mediciones de rendimiento bajo carga.

## Revisar cuando

- Cambien las series, los rangos o el contrato de exportación.
- Se incorpore JavaScript o cambie la política de contenido.
- Se requieran componentes nuevos, múltiples operadores o distintas plataformas.
- Las mediciones de uso identifiquen problemas de carga o renderizado.

## Referencias

- [Jinja: API, escape y caché de plantillas](https://jinja.palletsprojects.com/en/stable/api/).
- [Jinja2 3.1.6](https://pypi.org/project/Jinja2/3.1.6/).
- [MarkupSafe 3.0.3](https://pypi.org/project/MarkupSafe/3.0.3/).
