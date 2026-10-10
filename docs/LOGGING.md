# Logging y troubleshooting

La aplicación usa `logging` de la biblioteca estándar. Cada instancia escribe
el mismo diagnóstico JSON por línea en consola (`stderr`) y en
`DATA_DIR/logs/application.log`. El nivel predeterminado es INFO.

## Configuración

| Variable | Predeterminado | Valores |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`; admite minúsculas. |
| `LOG_MAX_BYTES` | `5242880` (5 MiB) | Entero desde 1024 bytes. |
| `LOG_BACKUP_COUNT` | `5` | Entero de 1 a 100. |

Las variables se leen al crear la aplicación. Un valor inválido impide iniciar
con una configuración ambigua. No se agregaron dependencias.
Para activar troubleshooting, iniciar la aplicación con `LOG_LEVEL=DEBUG`;
volver a INFO y reiniciar al terminar. Mantener una instancia y un worker.

El archivo actual rota por tamaño a `application.log.1`; se conservan hasta
cinco copias por defecto. La más antigua se reemplaza al rotar. La retención es
por tamaño, no por días, aproximadamente 30 MiB con los valores predeterminados.
Un registro individual mayor al tamaño configurado puede superar ese límite.
Los archivos se ubican bajo la misma ruta configurable de datos, preparada para
almacenamiento persistente; esta configuración no crea ni monta volúmenes.

## Contenido y niveles

Todos los registros incluyen fecha UTC, nivel, mensaje y operación. Cuando
corresponde, agregan ID de jornada, revisión, operación persistente, evento,
formato de descarga, fase o estado HTTP.

- **INFO:** inicialización y cierre del proceso, acciones confirmadas, proyección
  de eventos al historial y descargas generadas.
- **WARNING:** recuperación de datos, degradación del almacenamiento y avisos
  operativos. El estado de almacenamiento conserva sus advertencias.
- **ERROR:** acciones que no pudieron confirmarse, fallos del historial,
  exportaciones y errores HTTP inesperados.
- **DEBUG:** inicio y fases de una acción, publicación de revisión, rechazos por
  validación y solicitudes terminadas con estado y duración en milisegundos.

Los errores incluyen traceback estructurado: tipo de excepción y sus archivos,
funciones y líneas, incluida la cadena de causas. Se omiten mensajes de excepción,
líneas de código, variables locales, cuerpos, consultas y cabeceras. Las rutas HTTP
usan la plantilla de la ruta, sin valores de parámetros introducidos por el usuario.
Los nombres y detalles de negocio se consultan en Registros, no en el diagnóstico.

Ejemplo de configuración: `LOG_LEVEL=DEBUG LOG_MAX_BYTES=5242880 LOG_BACKUP_COUNT=5`.
El diagnóstico permite relacionar una operación con su revisión y su jornada;
el traceback identifica dónde investigar sin volcar su contenido privado.
Los logs propios de Uvicorn son independientes de estos archivos y configuración.

## Historial íntegro y fallos de escritura

`DATA_DIR/logs/actions/` conserva el historial de acciones y cierres; no se rota ni
se elimina automáticamente. Se mantiene aunque cambie LOG_LEVEL o roten los
archivos de diagnóstico. Su crecimiento requiere supervisión y copias de seguridad.
La pantalla Registros consulta este historial y los eventos pendientes durables.

Cada evento está vinculado a una operación confirmada. Si falla su archivo,
permanece pendiente en la revisión y se reintenta al reiniciar o en la siguiente
mutación válida; el ID de operación e índice evitan duplicaciones. El diagnóstico
no es la fuente para reconstruir la jornada: consultar [persistencia](PERSISTENCIA.md).

Si falla el archivo de diagnóstico, la aplicación avisa una vez por consola durante
ese incidente, continúa y reintenta en el siguiente registro habilitado por nivel.
Al recuperar el destino, avisa por consola. Los diagnósticos emitidos durante el
fallo no se almacenan para reproducirlos después; los eventos de negocio sí conservan
su mecanismo durable. Un fallo de consola tampoco interrumpe el guardado de negocio.
`/api/storage` expone `diagnostic_log_available` junto al estado del almacenamiento.
Un fallo del diagnóstico por sí solo no bloquea la aplicación; el daño de datos
esenciales conserva las restricciones de recuperación documentadas.

Ante un error HTTP inesperado antes de responder, se guarda diagnóstico y se
responde 500 con un mensaje genérico, sin contenido de la excepción. Si la respuesta
ya había comenzado, se registra y propaga el fallo al servidor ASGI. Los archivos
se cierran al apagar la aplicación mediante su ciclo de vida ASGI.
