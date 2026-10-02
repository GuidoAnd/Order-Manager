# ADR-002 — Persistencia local en JSON

## Estado
Aceptada

## Fecha
2026-09-29

## Contexto
En el MVP, las órdenes y autores pertenecen a una jornada temporal. Deben
conservarse entre reinicios las estadísticas globales de jornadas cerradas y
el catálogo de artículos. También se necesita exportar los datos de una
jornada al cerrarla.

## Decisión
Mantener la jornada activa, sus órdenes, autores y registros en memoria.
Guardar las estadísticas globales en `data/global_stats.json` y el catálogo
en `data/inventory.json`. Al cerrar correctamente una jornada, generar una
exportación JSON con sus datos y estadísticas. La última exportación solo se
conserva en memoria para permitir otra descarga durante esa ejecución.

Las escrituras de los archivos persistentes se realizan primero en un archivo
temporal del mismo directorio y después se reemplaza el archivo de destino.
El cierre guarda los acumulados globales antes de retirar la jornada activa.

## Motivos
- JSON es suficiente para dos conjuntos pequeños de datos persistentes y una
  exportación que debe poder leerse fuera de la aplicación.
- El modelo de una jornada activa permite calcular las estadísticas desde sus
  órdenes sin mantener una segunda copia persistente de cada cambio.
- La escritura con reemplazo reduce el riesgo de dejar un archivo parcial.
- Evita introducir una base de datos antes de necesitar consultas o acceso
  concurrente más complejo.

## Alternativas consideradas
- Persistir también la jornada activa: cambiaría su carácter temporal y
  exigiría definir recuperación tras fallos.
- Introducir MariaDB desde esta etapa: añade operación y mantenimiento para
  un volumen de datos que todavía no lo exige.
- Guardar todo únicamente en memoria: perdería el catálogo y los acumulados
  globales al reiniciar.

## Consecuencias
- La jornada activa y la última exportación se pierden al reiniciar el proceso.
- Los archivos JSON persistentes necesitan copias de seguridad externas si se
  requiere recuperación ante pérdida del disco.
- El estado en memoria y los archivos locales suponen una sola instancia de
  aplicación; varias instancias requerirían otra estrategia de persistencia.
- JSON no ofrece consultas relacionales ni transacciones entre varios archivos.

## Revisar cuando
- Se requieran varias instancias, acceso concurrente o consultas históricas.
- Sea necesario recuperar una jornada activa después de reiniciar.
- El volumen o las garantías de persistencia hagan conveniente MariaDB.
