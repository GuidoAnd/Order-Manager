# ADR-009 — Persistencia por acción, volúmenes y rollback

## Estado
Aceptada

## Fecha
2026-10-14

## Contexto
Las jornadas abiertas deben sobrevivir reinicios. Cada acción válida requiere
un estado coherente y el último cierre debe permitir recuperación exacta.
Este ADR actualiza y sustituye la decisión operativa del ADR-002 para v0.3.

## Decisión
Guardar bajo DATA_DIR revisiones JSON coordinadas con manifiesto vigente y
anterior, validación, hashes, escrituras temporales, sincronización y publicación
atómica. Confirmar la revisión antes de responder éxito. El historial operativo
se conserva separado; sus eventos enlazan acciones confirmadas, pero no sustituyen
los archivos completos necesarios para restaurar el estado.

Conservar snapshot inmediatamente anterior al último cierre. El rollback revierte
la jornada y sus acumulados, descarta la abierta tras confirmación y conserva
el catálogo vigente. Altas y precios aplican hacia adelante; las líneas históricas
conservan sus valores. La recuperación consume el snapshot y retira la descarga
del cierre revertido; el siguiente cierre produce nuevos archivos sin duplicar ventas.

Recuperar la última revisión íntegra cuando sea posible; aislar daños según el
componente y bloquear ante pérdida esencial sin restablecimiento silencioso.
El contenedor monta un directorio persistente elegido por el administrador y
DATA_DIR coincide con su destino. Mantener una instancia y un worker.

## Motivos
- Una publicación coherente evita combinar archivos de acciones distintas.
- El snapshot permite restaurar el momento previo al cierre sin inferirlo del log.
- El catálogo vigente conserva cambios válidos realizados hacia adelante.

## Alternativas consideradas
- Memoria temporal: pierde órdenes y recuperación al reiniciar.
- Reconstrucción únicamente desde logs: exige eventos completos y reproducción determinista.
- MariaDB inmediata: incrementa operación; se mantiene como evolución futura.

## Consecuencias
- Los volúmenes conservan datos, pero no son copias de seguridad ni coordinación.
- Copiar DATA_DIR con la aplicación detenida permite una copia coherente.
- La pérdida del disco requiere restauración externa.
- Para múltiples instancias se necesitan persistencia y concurrencia compartidas.

## Revisar cuando
- Se necesiten varios escritores, consultas históricas o mayores garantías transaccionales.

Consultar [persistencia](../arquitecture/PERSISTENCIA.md) y [Docker](../arquitecture/DOCKER.md).
