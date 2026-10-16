# Persistencia y recuperación — v0.3

La aplicación confirma cada acción válida mediante una revisión JSON íntegra.
La memoria es estado de trabajo; la recuperación usa archivos bajo `DATA_DIR`.
No requiere base de datos ni paquetes adicionales. Una instancia y un worker.

## Configuración y archivos

`DATA_DIR` es la ruta configurable de datos; el valor predeterminado es `data/`
junto al código. Debe ser escribible por el proceso. Preparar esa ruta no crea
un volumen ni configura Docker. En pruebas, `make_app(data_dir=...)` inyecta la ruta.

```text
data/
  current.json
  current.previous.json
  revisions/<revision_id>/
    inventory.json
    global_stats.json
    journey.json
    rollback.json
    last_export.json
    operation.json
  logs/actions/
  damaged/
```

El manifiesto referencia revisión vigente y anterior y sus hashes SHA-256.
La copia del manifiesto permite recuperar su referencia anterior si el vigente
está dañado. Cada componente incluye esquema `1`, revisión y contenido.
Las revisiones contienen catálogo, acumulados, jornada completa, seguimiento de
altas/precios, último snapshot recuperable, documento de descarga y operación.

Se guardan archivos y directorios con `fsync`; `os.replace` publica el manifiesto
atómicamente. El estado visible se confirma bajo un bloqueo. Los temporales son
auxiliares y no se usan como fuente de recuperación. Los conjuntos preparados
sin referencia confirmada no se cargan al arrancar.

La limpieza conserva las dos revisiones referenciadas; el snapshot del último
cierre se copia a las nuevas revisiones hasta recuperarlo o cerrar otra jornada.
El historial operativo y los archivos aislados no se limpian automáticamente.
El diagnóstico tiene [rotación propia](LOGGING.md); el historial de acciones no se rota.

## Inventario y órdenes

Los artículos nuevos de una acción válida se incorporan al catálogo, incluidos
los de órdenes no facturadas. Primero se valida toda la orden; no quedan altas
parciales. Borrar una orden o descartar su jornada conserva las altas.
Las categorías nuevas válidas de la API se incorporan con sus artículos.

Altas y cambios de precio afectan operaciones posteriores. Las líneas guardadas
conservan precios y totales; las órdenes de la jornada abierta admiten edición
explícita. Guardar el editor sin cambiar el precio no lo actualiza desde el catálogo.
Las líneas nuevas usan el catálogo vigente. Las no facturadas mantienen importes
nulos y no suman ventas, unidades ni promedios.

## Cierre y rollback

Un cierre publica juntos el estado previo recuperable, los acumulados, la última
exportación y la ausencia de jornada activa. El rollback restaura la jornada
inmediatamente anterior al cierre y sus acumulados anteriores. Conserva el
inventario vigente, incluidos artículos y precios posteriores.

Si existe una jornada abierta, se descarta sin contabilizar ventas. La advertencia
identifica ambas jornadas; Confirmar recuperación y Cancelar son acciones distintas.
La confirmación incluye ID de cierre, revisión y jornada abierta; el servidor
rechaza dobles envíos y confirmaciones desactualizadas.

La recuperación se consume y la jornada reabierta admite correcciones. El siguiente
cierre crea otro snapshot y contabiliza una sola vez. Se conservan los eventos del
cierre original, descarte y recuperación. El selector espera el nuevo cierre para
ofrecer archivos; las descargas ya realizadas permanecen como estaban.

`/api/journey/recovery` proporciona los datos de confirmación para
`POST /api/journey/recover`. La última descarga admite `close_id` además de
`journey_id` y `format`; los formularios incluyen el ID de cierre para rechazar
un selector antiguo incluso si se vuelve a cerrar la misma jornada.
El esquema de exportación sigue identificado como `v0.2` por compatibilidad;
la versión de la aplicación es `0.3`.

## Historial y fallos

Los eventos confirmados se guardan en `logs/actions/` con ID de operación, jornada,
secuencia y timestamp UTC. Los pendientes se conservan en la revisión y se
reintentan al arrancar o confirmar otra acción, sin duplicarlos. Los logs no
sustituyen el estado estructurado. Registros muestra el historial paginado.

Si una escritura falla antes de publicar, se conserva la última acción confirmada.
Si falla después de sustituir el manifiesto, se verifica y sincroniza su resultado;
si no puede confirmarse, se bloquean operaciones hasta reiniciar y verificarlo.
No se informa falsamente que un cierre publicado fue deshecho.

Al arrancar se valida esquema, integridad, referencias, precios, cantidades,
totales y relación entre cierre y acumulados. Una revisión esencial dañada permite
recuperar la anterior íntegra con advertencia de acciones no recuperadas. No se
mezclan archivos entre revisiones. Los dañados se aíslan en `damaged/` con un
registro del incidente cuando el almacenamiento permite hacerlo.

Un snapshot irrecuperable deshabilita rollback; una exportación dañada deshabilita
su descarga. Si faltan datos esenciales y no hay copia válida, no se inicializan
silenciosamente valores vacíos: la interfaz muestra diagnóstico y las operaciones
se bloquean. `/api/storage` informa disponibilidad, advertencias y revisión.
Un esquema desconocido se conserva y requiere una versión compatible.

## Migración y copias de seguridad

Con los JSON de v0.2 y sin manifiesto, el arranque valida e importa inventario y
acumulados a la primera revisión. Los originales se conservan; después el manifiesto
es la única referencia activa. Una instalación realmente nueva recibe el catálogo
inicial. La migración no recupera jornadas o descargas que v0.2 no guardó.

Para una copia consistente, detener la única instancia y copiar todo `DATA_DIR`,
incluidos manifiestos, revisiones e historial. Para restaurar, detener la aplicación,
conservar aparte los datos actuales y reponer una copia completa compatible.
Comprobar después las advertencias, la jornada y los acumulados antes de operar.
No editar a mano hashes ni ensamblar archivos de revisiones distintas.
Estas operaciones sobre datos se realizan con autorización del responsable.

La escritura durable depende también del sistema de archivos y almacenamiento.
Las pruebas de fallos simulados no acreditan todos los fallos físicos posibles.
