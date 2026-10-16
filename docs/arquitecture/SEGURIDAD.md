# Seguridad para uso local

La etapa actual está destinada a un dispositivo. Ejecutar el servicio en loopback
con el comando del README. La aplicación admite `localhost`, `127.0.0.1` y `::1`.
La comprobación del host no restringe por sí misma la interfaz donde escucha Uvicorn.

No hay autenticación: quien pueda acceder directamente al servicio puede operar
con la API. Antes de habilitar varios dispositivos deben implementarse los controles
de identidad, sesiones, HTTPS y concurrencia previstos en el
[ADR de seguridad y escalabilidad](../decisions/ADR-005-seguridad-local-y-escalabilidad.md).

## Límites

| Entrada | Límite |
| --- | --- |
| Cuerpo HTTP | 64 KiB, comprobados durante la recepción |
| Ruta y consulta | 8 KiB |
| Nombres y títulos nuevos | 200 caracteres |
| Categorías y subcategorías nuevas | 120 caracteres |
| Filtros de búsqueda | 200 caracteres |
| Campos procesados | 4096 |
| Líneas por orden | 50 |

Se rechazan caracteres de control en textos de negocio. Los datos históricos
se conservan; estas reglas se aplican al introducir o modificar valores.

## Formularios y API

Los formularios POST contienen un token generado por instancia. El token no
identifica al supervisor ni se guarda en archivos o logs. Después de un reinicio,
recargar las páginas antes de enviar formularios; varias pestañas son compatibles.

Las solicitudes que modifican datos rechazan orígenes distintos, incluidos puertos
diferentes, y solicitudes de navegador identificadas como procedentes de otro sitio.
No se habilita CORS. La API exige `Content-Type: application/json` cuando una
solicitud de modificación lleva cuerpo; admite clientes locales sin navegador.

Las respuestas de rechazo usan 400 para entradas ambiguas o inválidas, 403 para
protección de origen/token, 413 para cuerpos excesivos, 414 para URL excesiva y
415 para formatos no admitidos. La validación de estructura JSON conserva 422.
Ninguno de esos rechazos confirma una mutación de negocio.

## Respuestas y diagnóstico

Las cabeceras bloquean scripts, recursos externos y enmarcado. Los estilos
locales y embebidos se conservan. Las respuestas de negocio llevan `no-store`;
las descargas siguen disponibles y no modifican datos. Swagger y ReDoc requieren
scripts externos y no funcionan con esta política; consultar `/openapi.json`.

Los errores inesperados no muestran trazas ni rutas internas. Los errores de
validación no devuelven entradas completas. Los rechazos se registran con nivel,
operación, método y estado HTTP, sin cuerpo, cabeceras ni token.
La configuración de diagnóstico se describe en [logging](LOGGING.md).

Los límites de tamaño no sustituyen los límites de conexiones y tiempos del
servidor o del despliegue. La aplicación mantiene una instancia y un worker.
