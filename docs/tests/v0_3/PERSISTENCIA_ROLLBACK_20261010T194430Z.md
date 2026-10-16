# Persistencia y rollback — v0.3

Fecha UTC: **2026-10-10T19:44:30Z**. Resultado: **PASS**.

## Estado evaluado

Primer bloque de v0.3: guardado por acción, recuperación ante reinicios y rollback
de la última jornada. Los resultados corresponden al estado evaluado en esta fecha.

## Resultados

| Comprobación | Resultado |
| --- | --- |
| Suite completa de pytest | 311 PASS, 0 FAIL; 253,98 s |
| Casos nuevos de persistencia | 21 incluidos en la suite completa |
| Flujo nuevo de rollback en navegador | PASS en 320x568, 375x667, 430x932, 768x1024 y 1366x768 |
| Flujos anteriores y regresiones | PASS en la suite completa |
| Sintaxis Python y formato de cambios | PASS |
| Enlaces locales de documentación pública | PASS |

Comando, con Chromium y la configuración de fuentes del entorno disponibles:

```bash
.venv/bin/python -m pytest -q --tb=short --maxfail=2
```

Las pruebas usan datos temporales y un adaptador ASGI para Chromium, sin abrir
puertos. La configuración de fuentes pertenece al entorno de pruebas; no es
una nueva dependencia de la aplicación.

## Cobertura

- DATA_DIR, migración con originales conservados y restauración tras reinicios.
- Guardado de acciones válidas; órdenes inválidas sin altas parciales.
- Artículos persistentes al eliminar órdenes o descartar jornadas, incluidas no facturadas.
- Precios hacia adelante y edición explícita sin actualización implícita desde el catálogo.
- Edición de una línea cuyo artículo fue eliminado del inventario.
- Snapshot exacto previo al cierre, descarte de la jornada abierta y catálogo posterior conservado.
- Reversión de acumulados, reapertura, nuevo cierre y rechazo de recuperaciones repetidas.
- Descargas tras el nuevo cierre y rechazo de un selector ligado al cierre anterior.
- Fallos antes de publicar y después de sustituir el manifiesto; reconciliación o bloqueo.
- Fallos de escritura del historial con reintento, sin eventos duplicados.
- Corrupción de revisión, manifiesto y snapshot; copia anterior, aislamiento y diagnóstico.
- Esquemas desconocidos conservados, rutas internas acotadas y retención de dos revisiones.
- Confirmación, cancelación, advertencia, colores distintos y ausencia de desborde desde 320 px.

## Límites

Se mantiene una instancia y un worker. Las pruebas simulan fallos de escritura
y corrupción, sin acreditar todos los fallos físicos de almacenamiento.
Chromium emulado no acredita dispositivos físicos, otros motores, Docker ni
la ejecución en Intel Atom N270.
