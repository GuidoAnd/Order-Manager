# Arquitectura de Order Manager — v0.2 en desarrollo

## Propósito

Aplicación web para que un supervisor gestione jornadas, autores, órdenes y ventas. La v0.2 continúa el MVP integrado; v1.0 será la versión final prevista.

## Componentes y datos

El supervisor usa una interfaz HTML/CSS desde el navegador. FastAPI, ejecutado con Uvicorn sobre Python, gestiona la lógica de la aplicación. La jornada activa, sus órdenes, autores, registros y estadísticas se conservan en memoria. Al cerrar la jornada se genera una exportación JSON y se conserva temporalmente la última para permitir otra descarga durante la misma ejecución. Las estadísticas globales y el inventario inicial de artículos se guardan en archivos JSON separados y se recuperan al reiniciar la aplicación.

La aplicación ASGI se define en `order_manager/api.py`. El `api.py` de la raíz
solo expone ese mismo objeto `app` para herramientas que requieren un punto de
entrada en la raíz del repositorio.

## Módulos

- **Jornadas y autores:** creación, consulta, cierre y descarte de jornadas; autores asociados a cada jornada.
- **Órdenes y artículos:** cada orden pertenece a un autor y admite varias líneas de artículos con cantidad y precio unitario. El backend calcula los subtotales y el total. Se pueden consultar, modificar y eliminar órdenes. El catálogo inicial reúne categorías, subcategorías y productos persistentes; el formulario los agrupa para seleccionarlos. Los artículos creados en órdenes se ofrecen temporalmente para nuevas órdenes mientras alguna orden vigente los facture.
- **Artículos vendidos:** la sección Artículos muestra el «Catálogo vendido de la jornada», calculado desde las órdenes actuales y ordenado por unidades vendidas. Los artículos disponibles para nuevas órdenes se administran en una lista separada.
- **Ventas y estadísticas:** las cantidades de las órdenes suman unidades vendidas; el inventario inicial es un catálogo sin existencias físicas. Las órdenes, totales y artículos facturados se muestran por autor, además de los totales de jornada. Los acumulados globales conservan jornadas cerradas, órdenes, unidades e importe, con desglose por artículo y categoría.
- **Registros y exportación:** se registran acciones relevantes del supervisor y se exportan los datos de la jornada en JSON.

## Persistencia del catálogo

`data/inventory.json` se crea con los productos iniciales si aún no existe. Las altas,
ediciones y bajas realizadas en la administración del catálogo se escriben de
forma atómica. Cada jornada toma el catálogo vigente; los cambios de precio
afectan las nuevas líneas de orden, pero las líneas ya guardadas conservan su
precio y total. Un producto sin precio requiere completarlo al facturarlo.
Los artículos creados dentro de órdenes se derivan de las órdenes actuales:
desaparecen de las opciones al borrar o modificar su última orden. Si la
jornada se cierra correctamente, permanecen en el JSON exportado y en los
acumulados globales de ventas.

## Cierre y descarte

«Cerrar y contabilizar ventas» prepara la exportación JSON, incorpora la jornada una sola vez a las estadísticas globales y luego permite limpiar sus datos temporales. Si falla la exportación o el guardado, la jornada permanece disponible para reintentar.

Tras confirmar el cierre en la interfaz, una página transitoria solicita la descarga de la última exportación y redirige al Dashboard. También ofrece un enlace para repetir la descarga durante la misma ejecución.

«Descartar jornada sin contabilizar ventas» elimina sus datos temporales sin aumentar las estadísticas globales. Ambas acciones requieren confirmaciones claras y diferentes para evitar errores.

## Evolución prevista

El supervisor opera la plataforma sin autenticación. La autenticación y la persistencia de permisos se abordarán en una actualización menor posterior. CSV sigue previsto para v0.2; MariaDB se evaluará después de v1.0.

## Decisiones técnicas

- [FastAPI como servidor](decisions/ADR-001-FastApi.md).
- [Persistencia local en JSON](decisions/ADR-002-Json-persistance.md).
- [Exportación CSV prevista](decisions/ADR-003-csv-export.md).
- [Pruebas funcionales en móviles](decisions/ADR-004-mobile-testing.md).
