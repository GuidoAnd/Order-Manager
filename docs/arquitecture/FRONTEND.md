# Interfaz y plantillas de v0.3

## Presentación

HTML/CSS y Jinja2, sin JavaScript. `templating.py` configura escape automático,
`StrictUndefined` y hasta 128 plantillas compiladas. Los datos de negocio se
preparan por petición; las plantillas se distribuyen en `order_manager/templates`.
`safe` se reserva para fragmentos internos cuyos datos ya están escapados.

## Órdenes y líneas

| Ruta | Uso |
| --- | --- |
| `/ordenes` | Listado, búsqueda y Agregar nueva orden. |
| `/ordenes/nueva` | Creación. |
| `/ordenes/{id}/editar` | Edición. |
| `/ui/orders/form` | Guardado y acciones de agregar/quitar líneas. |

Cancelar vuelve al Dashboard sin guardar. Guardar conserva búsqueda, filtros y
página del listado. Agregar o quitar líneas no confirma cambios hasta Guardar
orden. Los errores conservan campos, autor y contexto; serie y numeración muestran
su error junto al control.

Cada línea elige Del inventario o Nuevo producto. CSS muestra los campos activos;
el servidor ignora los inactivos y valida categoría/subcategoría. Los artículos
sin precio requieren uno al facturarse. El editor incorpora las categorías
originales de órdenes creadas por API. Una línea de catálogo conserva su origen,
precio y referencia; un artículo retirado sigue disponible en ese editor.
Las nuevas categorías válidas de la API se registran con las altas del catálogo.

### Serie e identidad

| Serie | Numeración inclusiva |
| --- | --- |
| 10 | 001–080 |
| 20 | 081–160 |

La selección es manual y repetible, incluso para un mismo autor. Los números se
guardan como enteros y se muestran con tres dígitos; no se incrementan ni se
crean otras series. El ID de la orden y el contador cronológico son automáticos.
POST/PUT de órdenes exige `series` y `serial_number`, además del autor y líneas:

```json
{
  "author_id": "ID_DEL_AUTOR",
  "series": "20",
  "serial_number": 81,
  "status": "sale",
  "lines": [{"catalog_id": "ID_DEL_ARTICULO", "quantity": 1, "unit_price": 100}]
}
```

Cada línea nueva recibe `line_id` del servidor. Devolverlo en PUT conserva su
identidad al reordenar referencias repetidas o quitar otras líneas; duplicados
e identificadores ajenos se rechazan. Una línea nueva omite el identificador.
Los formularios lo transportan en campos ocultos. Las solicitudes antiguas siguen
admitidas, con correspondencia por posición para referencias repetidas sin ID.
Las órdenes previas sin el campo reciben referencias estables en el editor y
solo las confirman al guardar. Serie, numeración e identificadores sobreviven a
reinicio y rollback, y se incluyen en el JSON; los CSV agregados no cambian.

### Ventas y no facturadas

Una orden contiene de 1 a 50 líneas con cantidades positivas. Una venta exige
precios naturales; los subtotales y el total se calculan con enteros. Cantidad y
precio tienen un máximo de `9223372036854775807` y rechazan booleanos.

No facturada (regalo/cancelada) exige artículos y cantidades, pero guarda precios,
subtotales y total nulos. No aporta ventas, unidades ni promedios. Cambiar el tipo
conserva ID y número; volver a venta requiere precios válidos. Sus artículos nuevos
también se incorporan al catálogo persistente. Las líneas históricas conservan
sus precios frente a cambios posteriores del catálogo.

## Búsquedas y paginación

El tamaño habitual es 2 filas hasta 374 px, 3 hasta 650 px, 4 hasta 1023 px y
5 desde 1024 px. CSS muestra una sola vista. Hasta 650 px, los listados se
presentan como fichas con etiquetas y sin desplazamiento lateral de página.
Los filtros y las páginas afectan la presentación, no los cálculos completos.

- **Órdenes:** página compartida que reserva una orden de cada autor con órdenes
  restantes y completa por número. Si faltan lugares, amplía el tamaño para
  incluirlos. La búsqueda usa cinco resultados por página; coincide parcialmente
  con nombres sin distinguir acentos/mayúsculas y admite números de serie.
  `#n` busca por contador interno. El filtro por identidad de artículo se combina
  con la búsqueda. Editar, borrar y corregir errores conserva ese contexto.
- **Artículos:** búsqueda parcial por nombre y filtros de categoría/subcategoría.
  Filtra y ordena una vez por petición para las cuatro vistas. Altas y ediciones
  usan desplegables validados. Un enlace de edición inexistente devuelve 404.
- **Catálogo vendido:** orden por unidades descendentes y nombre; muestra unidades
  e importe. Su página es independiente del inventario y conserva sus filtros.
- **Registros:** historial de acciones del más reciente al más antiguo, con fecha,
  acción y detalle. Consultarlo no genera eventos ni modifica descargas.

Las páginas fuera de rango se ajustan. Las reglas de visibilidad viajan en el
HTML y la URL del CSS incluye un hash para evitar listas duplicadas por una
hoja antigua.

## Jornada y autores

Cada autor tiene tablas independientes de órdenes, bloques de hasta diez ventas
y artículos facturados. Los acumulados se calculan antes de paginar. Cada bloque
muestra cantidad, subtotal y los números reales de sus órdenes; editar o borrar
recalcula los bloques. Las otras páginas se conservan al navegar.

Los enlaces omiten páginas iguales a 1. Si la consulta supera 4096 caracteres,
se usa un token por instancia y la tabla de destino. El estado está asociado a
la jornada, caduca a los 30 minutos y admite hasta 64 entradas y 32768 selecciones
totales. Al alcanzar el límite se expulsan los estados menos recientemente
consultados. Un estado individual excesivo devuelve 413. Un enlace caducado,
expulsado, de otra jornada o perdido al reiniciar muestra un aviso y restablece
las páginas. Este estado guarda solo navegación y no modifica DATA_DIR.

Editar nombre cambia únicamente el título de la jornada abierta. El formulario
envía su ID; un formulario desactualizado o sin ID devuelve 409. Los autores se
administran mediante Agregar autor y Editar autores; sus nombres quedan visibles
con los formularios cerrados. Renombrar conserva IDs y órdenes; no se admite
borrar autores con órdenes. Los errores conservan el texto y el editor abierto.

La finalización está antes de Autores y Resultados. Cierre, descarte y recuperación
usan confirmación; su comportamiento se detalla en [persistencia](PERSISTENCIA.md).
Después del cierre se elige JSON, CSV resumen, CSV detallado o ZIP, sin descarga
automática. Registros ofrece el mismo selector dentro de Descargar última jornada,
cerrado por defecto. Repetir descargas no vuelve a contabilizar ventas.

## Accesibilidad y mantenimiento

Hasta 1023 px, Menú despliega las cinco secciones; desde 1024 px, los enlaces
permanecen visibles. `details`/`summary` admite toque y teclado. Las acciones
próximas usan colores diferentes y áreas táctiles de al menos 44 px. En móvil,
Guardar orden ocupa más espacio que Agregar y Quitar artículo.

Los cambios se validan en 320×568, 375×667, 430×932, 768×1024 y 1366×768.
La [seguridad](SEGURIDAD.md) protege formularios y contenido; [ADR-006](../decisions/ADR-006-jinja2-e-interfaces-de-ordenes.md)
registra la decisión de presentación y sus límites.
