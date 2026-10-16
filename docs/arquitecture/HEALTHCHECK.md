# Comprobación de salud

`GET /api/health` comprueba la disponibilidad de la aplicación y su persistencia.
La respuesta contiene `status`, `checks` e `issues`, sin rutas del almacenamiento,
contenido de archivos ni mensajes de excepción.

| Estado | HTTP | Significado |
| --- | --- | --- |
| `healthy` | 200 | Inicialización, revisión esencial y lectura/escritura de DATA_DIR correctas. |
| `degraded` | 200 | El negocio puede operar; hay advertencias, daño opcional, historial pendiente o diagnóstico no disponible. |
| `unavailable` | 503 | Inicialización, revisión esencial o lectura/escritura no disponibles. |

La comprobación ocurre bajo el bloqueo de la aplicación:

- Verifica que el manifiesto en disco coincida con la revisión activa.
- Lee los componentes, comprueba hashes, esquema, referencias y coherencia de
  inventario, acumulados y jornada. Daño de rollback/última descarga es opcional.
- Crea un temporal `.health-*.tmp` directamente en DATA_DIR, escribe, sincroniza,
  lee y elimina el archivo; comprueba también la sincronización del directorio.
- No publica revisiones, modifica jornadas, repara archivos, aísla daños ni
  cambia inventario o estadísticas. El diagnóstico se guarda aparte en logs.

Si falla la limpieza del temporal, responde 503; ese archivo puede permanecer
hasta resolver el problema. No se usa como estado recuperable ni se mezcla con
las revisiones. Un estado degradado conserva la información de recuperación y
los eventos pendientes; consultar [persistencia](PERSISTENCIA.md).

## Script HTTP

Desde el directorio de la aplicación:

```bash
.venv/bin/python -m order_manager.healthcheck
```

En un contenedor con Python disponible se usa `python -m order_manager.healthcheck`.
El Dockerfile integra este comando como HEALTHCHECK.

El destino predeterminado es `http://127.0.0.1:8000/api/health`. Se puede cambiar
mediante `HEALTHCHECK_URL` o `--url`; solo admite HTTP local, ruta `/api/health`, sin
credenciales, query ni fragmentos. No sigue redirecciones ni usa proxies del entorno.
No consulta el host, red externa, servicios del sistema ni requiere privilegios.
El puerto corresponde al servidor de la aplicación ya iniciado; el script no lo abre.

| Parámetro | Predeterminado | Rango |
| --- | --- | --- |
| `--timeout` | 3 segundos por operación HTTP | Mayor que 0 y hasta 30. |
| `--attempts` | 3 | 1 a 10. |
| `--delay` | 1 segundo entre intentos fallidos | 0 a 10. |

Los intentos proporcionan margen para el arranque. Una respuesta `healthy` o
`degraded` termina con código 0; una respuesta inválida, incompleta, 503 o fallo HTTP
se reintenta y termina con código 1 si no se recupera. La salida JSON muestra
estado e intentos usados. La respuesta está limitada a 64 KiB. El timeout acota
las operaciones HTTP, no garantiza detectar cualquier bloqueo funcional.

## Registro y límites

El endpoint registra el primer estado, cambios y estados degradados/fallidos en
el [diagnóstico persistente](LOGGING.md). No repite éxitos idénticos. Al reiniciar,
el primer resultado vuelve a registrarse. DEBUG puede añadir el diagnóstico de
cada solicitud según la configuración elegida.

Si el script no consigue confirmar disponibilidad HTTP, guarda un diagnóstico
sin URL ni detalles sensibles en `DATA_DIR/logs/healthcheck.log`, con la misma
política configurable de nivel y rotación. Ese archivo está separado del escritor
de la aplicación. Ejecutar una sola comprobación de script a la vez.
La configuración de DATA_DIR debe coincidir con la del servidor; si falla el
archivo de diagnóstico, continúa mostrando el resultado por consola.
Los fallos repetidos del script se registran; sus éxitos alcanzables se registran
por el endpoint, evitando dos escritores del archivo de aplicación.

Esta comprobación no modifica automáticamente el estado del negocio ni garantiza
que todos los flujos funcionales estén libres de errores. Tampoco comprueba equipos
físicos, conectividad externa o infraestructura. Mantener una instancia y un worker.
