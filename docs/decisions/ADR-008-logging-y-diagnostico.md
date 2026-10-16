# ADR-008 — Logging y diagnóstico operativo

## Estado
Aceptada

## Fecha
2026-10-14

## Contexto
La persistencia y los flujos HTTP requieren diagnóstico de errores sin exponer
entradas ni confundir el historial del supervisor con archivos de troubleshooting.

## Decisión
Usar logging de la biblioteca estándar, eventos JSON con timestamp UTC, consola
y DATA_DIR/logs/application.log. INFO es el valor predeterminado; LOG_LEVEL=DEBUG
agrega fases y tiempos técnicos. Rotar a 5 MiB con cinco copias. El historial de
acciones y cierres permanece íntegro y separado.

Los errores registran tipo y ubicación técnica, sin mensajes sensibles ni datos
de formularios. Los fallos del archivo diagnóstico avisan por consola y se
reintentan sin bloquear el negocio. Los eventos operativos pendientes se guardan
durablemente y su reproducción evita duplicados.

## Motivos
- La biblioteca estándar satisface diagnóstico y rotación sin dependencias nuevas.
- DEBUG permite troubleshooting con un contrato explícito de información.
- Separar diagnóstico e historial conserva las acciones aunque roten los logs.

## Alternativas consideradas
- Guardar solo consola: dificulta revisar fallos anteriores.
- Rotar el historial junto al diagnóstico: puede perder acciones del supervisor.
- Registrar entradas y excepciones completas: puede exponer información sensible.

## Consecuencias
- La rotación limita el diagnóstico local; el historial tiene crecimiento independiente.
- Un fallo de logging no sustituye ni invalida la confirmación persistente de negocio.
- El administrador configura DEBUG y protege el directorio de datos.

## Revisar cuando
- Se requiera agregación externa, retención regulada o varios procesos.

Consultar [logging](../arquitecture/LOGGING.md).
