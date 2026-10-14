# Interfaz y plantillas de v0.3

La presentación usa HTML/CSS y Jinja2, sin JavaScript. Los archivos de
`order_manager/templates` se distribuyen junto con el código; su ubicación se
resuelve desde el módulo y no depende del directorio de ejecución.
`templating.py` configura escape automático, comprobación de contexto y una
caché de plantillas compiladas. Los datos de negocio se preparan en cada petición.

## Órdenes

- `/ordenes`: listado, búsqueda y paginación; Agregar nueva orden aparece arriba.
- `/ordenes/nueva`: formulario de creación.
- `/ordenes/{id}/editar`: formulario de edición con datos existentes.
- `/ui/orders/form`: guardado y acciones de agregar/quitar artículos.

Cancelar vuelve al Dashboard sin confirmar cambios. Guardar vuelve al listado
con su búsqueda, filtros y página. Un error conserva los campos; los errores de
serie y numeración se asocian al control correspondiente. Las líneas agregadas o
quitadas no confirman una orden hasta usar Guardar orden.

Cada formulario exige elegir una serie y escribir el número:

| Serie | Rango inclusivo |
| --- | --- |
| 10 | 001–080 |
| 20 | 081–160 |

Se permiten repeticiones. No se generan ni incrementan esos números y no existe
alta de otras series. El número se guarda como entero y se muestra con tres
dígitos. El ID automático permanece al editar; el contador interno conserva el
orden cronológico. La búsqueda por número admite la numeración manual, incluso
cuando se repite; `#n` busca por contador interno.

La API POST/PUT de órdenes requiere `series` y `serial_number`, además de sus
campos anteriores. Por ejemplo:

```json
{
  "author_id": "ID_DEL_AUTOR",
  "series": "20",
  "serial_number": 81,
  "status": "sale",
  "lines": [{"catalog_id": "ID_DEL_ARTICULO", "quantity": 1, "unit_price": 100}]
}
```

El servidor valida la relación entre serie y número. Las órdenes previas sin
serie siguen siendo legibles; al editarlas desde el formulario se eligen los
campos manuales. No se asignan datos al historial automáticamente.

Los nuevos campos sobreviven a reinicios y rollback, y forman parte del JSON
de cierre. El esquema v0.2 incorpora esos campos en las órdenes asignadas;
los CSV agregados mantienen su formato y los archivos ZIP incluyen el JSON.

## Jornada y Artículos

La finalización aparece debajo del bloque principal de Jornada, antes de Autores
y Resultados. Sus confirmaciones se conservan. Artículos mantiene las acciones
de edición y eliminación y sus filtros; el acceso Ver órdenes que lo usan no
se presenta en esa sección.

## Seguridad y mantenimiento

Los textos se escapan en las plantillas. `safe` se usa únicamente para fragmentos
internos previamente construidos con datos escapados; no usarlo con valores
procedentes de solicitudes. El token y las cabeceras del
[punto de seguridad](SEGURIDAD.md) se conservan.

Las plantillas, sus macros y las funciones de contexto tienen responsabilidades
separadas. Los cambios de presentación deben validarse en los cinco tamaños
habituales, desde 320 px. La decisión y sus límites están en
[ADR-006](decisions/ADR-006-jinja2-e-interfaces-de-ordenes.md).
