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

## Actualización — v0.3.1, 2026-10-31

Persistir las tandas de cada autor y las referencias de sus órdenes dentro de
las mismas revisiones JSON. Validar pertenencia, serie, numeración y única tanda
abierta. Confirmar aperturas y cierres por acción, con la atomicidad existente.

Al finalizar la jornada, cerrar las tandas abiertas en el documento exportado
con la misma fecha de cierre; conservar las fechas de las ya cerradas. Guardar
para rollback el estado anterior exacto, sin aplicar esos cierres a su snapshot.
Recuperar restaura las tandas previamente abiertas. Un fallo de exportación o
persistencia no confirma el cierre parcial.

Aceptar datos anteriores sin asignar tandas retrospectivamente ni reescribir
exportaciones. Mantener esquema persistido `1` y formato de descarga `v0.2`, con
campos adicionales cuando corresponda. Una vuelta de versión exige restaurar
una copia completa compatible: el código anterior desconoce estas referencias.
Los borradores del editor no son órdenes confirmadas y permanecen fuera de la
persistencia, según [ADR-006](ADR-006-jinja2-e-interfaces-de-ordenes.md).

## Revisar cuando
- Se necesiten varios escritores, consultas históricas o mayores garantías transaccionales.

Consultar [persistencia](../arquitecture/PERSISTENCIA.md) y [Docker](../arquitecture/DOCKER.md).
