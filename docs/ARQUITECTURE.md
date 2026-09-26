# Arquitectura de Order Manager — v0.1

## Propósito

Aplicación web para que un supervisor gestione jornadas, autores, órdenes y ventas. La v0.1 ofrece todos los módulos del MVP desde el inicio para probarlos juntos; v1.0 será la versión final del MVP.

## Componentes y datos

El supervisor usa una interfaz HTML/CSS desde el navegador. FastAPI, ejecutado con Uvicorn sobre Python, gestiona la lógica de la aplicación. La jornada activa, sus órdenes, autores, registros y estadísticas se conservan en memoria. Al cerrar la jornada se genera una exportación JSON y se conserva temporalmente la última para permitir otra descarga durante la misma ejecución. Las estadísticas globales se guardan por separado en un archivo JSON local y se recuperan al reiniciar la aplicación.

## Módulos

- **Jornadas y autores:** creación, consulta, cierre y descarte de jornadas; autores asociados a cada jornada.
- **Órdenes y artículos:** cada orden pertenece a un autor y admite varias líneas de artículos con cantidad y precio unitario. El backend calcula los subtotales y el total. Se pueden consultar, modificar y eliminar órdenes.
- **Ventas y estadísticas:** las cantidades de las órdenes suman unidades vendidas; no hay inventario inicial ni descuento de existencias. Se muestran estadísticas por autor y jornada. Los acumulados globales conservan jornadas cerradas, órdenes, unidades e importe, con desglose por artículo y categoría.
- **Registros y exportación:** se registran acciones relevantes del supervisor y se exportan los datos de la jornada en JSON.

## Cierre y descarte

«Cerrar y contabilizar ventas» prepara la exportación JSON, incorpora la jornada una sola vez a las estadísticas globales y luego permite limpiar sus datos temporales. Si falla la exportación o el guardado, la jornada permanece disponible para reintentar.

Tras confirmar el cierre en la interfaz, una página transitoria solicita la descarga de la última exportación y redirige al Dashboard. También ofrece un enlace para repetir la descarga durante la misma ejecución.

«Descartar jornada sin contabilizar ventas» elimina sus datos temporales sin aumentar las estadísticas globales. Ambas acciones requieren confirmaciones claras y diferentes para evitar errores.

## Evolución prevista

En v0.1 el supervisor opera la plataforma sin autenticación. La autenticación y la persistencia de permisos se abordarán en una actualización menor posterior. CSV está previsto antes de v1.0; el inventario y MariaDB se evaluarán después de v1.0.
