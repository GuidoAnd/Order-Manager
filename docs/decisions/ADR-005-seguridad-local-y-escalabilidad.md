# ADR-005 — Seguridad local y evolución hacia red local y nube

## Estado

Aceptada para uso local desde un dispositivo. Las etapas de red local y nube
requieren implementación y validación antes de habilitar esos entornos.

## Fecha

2026-10-11

## Contexto

El MVP permite administrar jornadas, autores, artículos, órdenes y exportaciones.
Su uso inicial se realiza desde un dispositivo. La evolución prevista comprende
varios dispositivos en una red local y, posteriormente, despliegues en nube.

La aplicación no dispone de autenticación ni permisos por operador. El estado
persistente en JSON y el bloqueo de negocio requieren una instancia y un worker.
Las confirmaciones de cierre, descarte y recuperación protegen la intención de
la operación, pero no identifican a quien la solicita.

## Decisión

Implementar controles de entrada y de navegador para el uso inicial desde un
solo dispositivo, mediante FastAPI, Starlette y la biblioteca estándar de Python.
Mantener el servicio vinculado a loopback según el comando de ejecución local.
Aceptar los hosts `localhost`, `127.0.0.1` y `::1`; esta comprobación no modifica
la interfaz de red del servidor ni sustituye su configuración de escucha.

- Limitar el cuerpo HTTP a 64 KiB durante su recepción, sin depender únicamente
  de `Content-Length`. Limitar ruta y consulta a 8 KiB.
- Validar las nuevas entradas de negocio con reglas comunes para API y
  formularios: nombres y títulos de hasta 200 caracteres; categorías y
  subcategorías de hasta 120; sin caracteres de control. Limitar los filtros de
  búsqueda a 200 caracteres. Conservar las restricciones numéricas y el máximo
  de 50 líneas por orden.
- Exigir un token aleatorio en cada formulario POST. Generarlo por instancia,
  mantenerlo fuera de archivos y registros, compararlo en tiempo constante y
  renovarlo al reiniciar. Comprobar el origen exacto de las solicitudes que
  modifican datos cuando el navegador lo proporciona y rechazar solicitudes
  identificadas como procedentes de otro sitio.
- Exigir `application/json` en solicitudes con cuerpo que modifican la API.
  Conservar el acceso de clientes locales sin navegador. No habilitar CORS.
- Rechazar cabeceras de seguridad ambiguas y campos de formulario duplicados.
  Limitar el número de campos procesados a 4096.
- Aplicar `Content-Security-Policy`, `X-Content-Type-Options`, `X-Frame-Options`
  y `Referrer-Policy`. Bloquear scripts, recursos externos, enmarcado y cambios
  de URL base; permitir los estilos locales y los estilos embebidos actuales.
  Aplicar `Cache-Control: no-store` a las respuestas de negocio.
- Conservar el escape de HTML, las confirmaciones y la validación de revisión
  para rollback. Los errores de validación no incluyen el valor original ni
  contexto del analizador; los errores inesperados mantienen una respuesta
  genérica y diagnóstico técnico. Los rechazos de seguridad no registran tokens,
  cabeceras ni cuerpos de solicitud.

Los límites se aplican a entradas nuevas. No modificar registros históricos ni
invalidar automáticamente datos persistidos antes de esta decisión.

## Motivos

- Limitar recursos antes de procesar entradas reduce el impacto de solicitudes
  excesivas y evita reglas diferentes entre API y formularios.
- El token y la comprobación de origen protegen las operaciones del navegador
  frente a envíos desde otros sitios, incluso en un servicio utilizado localmente.
- La comprobación del host limita solicitudes dirigidas a nombres externos que
  resuelvan hacia el servicio local.
- Las cabeceras restringen la interpretación y ejecución de contenido sin cambiar
  los controles nativos de HTML ni introducir JavaScript.
- La evolución por etapas permite incorporar controles de identidad, concurrencia
  y operación antes de ampliar la superficie de acceso.

## Alternativas consideradas

- Depender de validaciones del navegador: no protege la API ni solicitudes
  construidas fuera de la interfaz.
- Usar únicamente cabeceras de origen: no cubre todos los envíos de formularios
  ni sustituye un token de protección.
- Implementar autenticación y despliegue de nube en esta etapa: excede el alcance
  del uso inicial y requiere decisiones sobre operadores, sesiones e infraestructura.
- Añadir dependencias de seguridad: los controles actuales pueden implementarse
  con las dependencias existentes y la biblioteca estándar.

## Consecuencias

- La aplicación continúa sin autenticación. Los procesos y usuarios con acceso
  directo al servicio local pueden operar mediante la API. El token de formulario
  no constituye una credencial ni un permiso.
- Un formulario abierto antes de reiniciar requiere recargar la página para
  obtener el token vigente. Varias pestañas de la misma instancia son compatibles.
- Los clientes de la API deben enviar JSON cuando la operación lleva cuerpo.
- Los nombres de host externos y las direcciones LAN no se admiten en esta etapa.
- La política de contenido bloquea scripts y recursos externos, incluidos los
  utilizados por las páginas interactivas de Swagger y ReDoc. El esquema JSON
  continúa disponible en `/openapi.json`.
- Estos controles no proporcionan límites de conexiones, tiempos de transporte
  ni protección completa frente a denegación de servicio.
- JSON continúa requiriendo una instancia y un worker. Agregar dispositivos no
  habilita múltiples escritores ni garantiza resolución de ediciones simultáneas.

## Implementaciones futuras

### Etapa 2 — Varios dispositivos en una red local

Antes de ampliar el acceso:

- Implementar autenticación del supervisor, gestión segura de contraseñas,
  sesiones con caducidad y cierre de sesión, y cookies con atributos adecuados.
- Vincular los tokens de formulario a las sesiones autenticadas y aplicar
  autorización a cada operación de API e interfaz.
- Proporcionar HTTPS y definir explícitamente los hosts y orígenes permitidos.
  La pertenencia a una red local no constituye autorización.
- Resolver ediciones simultáneas con versiones y detección de conflictos para
  evitar sobrescribir cambios realizados desde otro dispositivo.
- Validar recuperación y copias de seguridad antes de habilitar el uso compartido.

### Etapa 3 — Entornos de nube

Antes de publicar el servicio:

- Definir usuarios, roles y permisos con privilegios mínimos, aplicados en el servidor.
- Establecer gestión y rotación de secretos fuera del código y de los registros.
- Configurar HTTPS, sesiones, hosts y orígenes para el entorno de despliegue.
- Revisar persistencia y concurrencia; evaluar MariaDB antes de admitir varias
  instancias o workers. Un volumen compartido no habilita escritores concurrentes.
- Establecer copias de seguridad y ensayos de restauración, monitoreo, límites
  de conexiones y solicitudes, actualizaciones y protección del despliegue.
- Validar aislamiento de datos y auditoría de acciones por operador.

Estas etapas describen condiciones necesarias; su implementación no forma parte
del punto 4 actual y requiere decisiones específicas sobre alcance y despliegue.

## Revisar cuando

- Se habilite acceso desde otro dispositivo o se necesite restringir operadores.
- Se incorpore autenticación, JavaScript, un proxy o un nuevo origen de acceso.
- Se requieran varias instancias, workers o una base de datos.
- Cambien los requisitos de disponibilidad, confidencialidad o auditoría.

## Referencias

- [OWASP: protección contra CSRF](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).
- [OWASP: cabeceras HTTP](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html).
