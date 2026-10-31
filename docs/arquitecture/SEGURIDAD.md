# Seguridad para uso local

El valor predeterminado permite `localhost`, `127.0.0.1` y `::1`, con el servicio
publicado en loopback. Se admite una excepción temporal para varios dispositivos
de una red local mediante hosts adicionales explícitos.

No hay autenticación: quien alcance el servicio puede operar como supervisor.
La excepción no incorpora identidad, sesiones ni HTTPS. El editor HTML de v0.3.1
detecta sobrescrituras desde formularios antiguos y reenvíos, pero no ofrece
autenticación ni control de versiones obligatorio para todos los clientes API.
Las etapas de seguridad con identidad y concurrencia compartida están definidas en el
[ADR de seguridad y escalabilidad](../decisions/ADR-005-seguridad-local-y-escalabilidad.md).

## Excepción temporal de hosts

`ALLOWED_HOSTS` agrega IP o nombres del servidor, separados por comas. Identifica
las direcciones usadas en la URL, no los equipos clientes. Los tres hosts de
loopback permanecen habilitados para operación y healthcheck. La configuración
se lee al crear la aplicación; un cambio requiere reiniciar el proceso.

En `deployment.env`, reemplazar la IP del ejemplo por la IP LAN del servidor:

```dotenv
ALLOWED_HOSTS=192.168.1.50,order-manager.local
APP_BIND_HOST=192.168.1.50
APP_PORT=8000
```

El nombre es opcional y debe resolver al servidor en la red. Los hosts se comparan
exactamente, sin distinguir mayúsculas; las IP se normalizan. No se admiten URL,
puertos ni comodines en `ALLOWED_HOSTS`; las IPv6 se escriben sin corchetes.
Una configuración inválida impide crear la aplicación antes de abrir los datos.

`APP_BIND_HOST` configura únicamente la publicación de Compose y `APP_PORT` el
puerto de acceso. Aceptar un host no abre puertos, no modifica firewall ni restringe
la IP del cliente. La operación continúa en una instancia y un worker.
Los tokens, origen exacto, límites y cabeceras siguientes también rigen en LAN.

### Aplicar con Docker Compose

Usar el `compose.json` actualizado y una imagen que admita `ALLOWED_HOSTS`.
Si la imagen instalada es anterior a ese soporte, reconstruirla y actualizarla
en el equipo de destino. Una imagen compatible no requiere reconstrucción al
cambiar únicamente estas variables de entorno.

Desde la raíz de la aplicación, recrear el contenedor usando la imagen local:

```bash
docker compose --env-file deployment.env -f compose.json \
  up -d --no-build --pull never --force-recreate
```

Abrir `http://192.168.1.50:8000` desde los equipos de la LAN, utilizando la IP y
el puerto configurados. El nombre del ejemplo también permite acceder mediante
`http://order-manager.local:8000` cuando resuelva al servidor. Recargar las páginas
abiertas después de recrear el contenedor para obtener el token vigente.

### Ejecutar directamente con Uvicorn

Uvicorn debe escuchar en la IP LAN mediante `--host`:

```bash
ALLOWED_HOSTS=192.168.1.50 .venv/bin/python -m uvicorn api:app \
  --host 192.168.1.50 --port 8000 --workers 1
```

### Volver al acceso local

En `deployment.env`:

```dotenv
APP_BIND_HOST=127.0.0.1
ALLOWED_HOSTS=
```

Repetir el comando de recreación de Compose. Con Uvicorn, retirar la variable
y volver a escuchar en `127.0.0.1`. La jornada y los datos persistentes se conservan.

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
