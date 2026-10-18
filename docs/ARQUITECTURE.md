# Arquitectura de Order Manager — v0.3

Versión cerrada documentalmente el 2026-10-18. El
[resumen de versión](version/v0_3.md) registra el alcance y la validación final.

## Componentes

Navegador → HTML/CSS y Jinja2 → FastAPI/Uvicorn → Store → revisiones JSON en DATA_DIR.
El supervisor gestiona jornadas, autores, catálogo, órdenes, ventas y descargas.

| Componente | Responsabilidad |
| --- | --- |
| `api.py` de la raíz | Expone la aplicación ASGI definida en `order_manager/api.py`. |
| `order_manager/api.py` | Rutas JSON, formularios y ciclo de vida. |
| `store.py` | Reglas de negocio, bloqueo y confirmación de acciones. |
| `persistence.py`, `state_validation.py` | Revisiones coordinadas, integridad y recuperación. |
| `journey_export.py`, `export_formats.py` | Documento de cierre y formatos JSON, CSV y ZIP. |
| `web.py`, `templating.py`, `templates/` | Contextos y presentación con escape HTML. |
| `journey_results.py`, `table_pages.py`, `journey_navigation.py` | Consultas paginadas y navegación. |
| `runtime_logging.py`, `health.py`, `healthcheck.py` | Diagnóstico y comprobación de disponibilidad. |
| `security.py`, `input_validation.py` | Controles HTTP y validación compartida. |

## Modelo y persistencia

Existe una sola jornada activa. Sus autores tienen órdenes de 1 a 50 líneas;
el backend calcula subtotales y estadísticas. Las órdenes no facturadas conservan
artículos y cantidades, pero no aportan ventas. Los artículos del catálogo no
representan existencias físicas.

Cada acción válida confirma catálogo, acumulados, jornada, recuperación y última
exportación como una revisión coherente antes de responder éxito. La memoria es
estado de trabajo; al reiniciar se restaura la revisión confirmada. Las altas y
precios del catálogo afectan operaciones posteriores; las líneas guardadas
conservan sus valores salvo edición explícita.

El cierre conserva un snapshot previo. Recuperarlo revierte el cierre y sus
acumulados, descarta la jornada abierta tras confirmación y conserva el catálogo
vigente. Los archivos nuevos se generan al cerrar otra vez. El historial de
acciones es durable y está separado del diagnóstico rotado.

## Operación y límites

- Una instancia y un worker: el `RLock` y el estado de trabajo pertenecen al proceso.
  Un volumen compartido no coordina escritores.
- DATA_DIR configurable y escribible; copias completas con la aplicación detenida.
  Un volumen y las descargas no sustituyen una copia de seguridad.
- Acceso por loopback de forma predeterminada, sin autenticación. `ALLOWED_HOSTS`
  permite hosts adicionales como excepción temporal para una LAN; Compose configura
  la publicación mediante `APP_BIND_HOST`. Identidad y control de conflictos siguen
  fuera del alcance implementado, según ADR-005.
- HTML/CSS sin JavaScript, con formularios del servidor y uso desde 320 px.
- Solo la última exportación está disponible en el servidor; los acumulados no
  constituyen un archivo completo de todas las órdenes históricas.

## Guías técnicas

| Guía | Contenido |
| --- | --- |
| [Persistencia](arquitecture/PERSISTENCIA.md) | Archivos, integridad, rollback, migración y copias. |
| [Interfaz](arquitecture/FRONTEND.md) | Formularios, series, líneas, búsquedas y paginación. |
| [Logging](arquitecture/LOGGING.md) | INFO/DEBUG, rotación e historial de acciones. |
| [Healthcheck](arquitecture/HEALTHCHECK.md) | Estados, script HTTP y diagnóstico. |
| [Seguridad](arquitecture/SEGURIDAD.md) | Límites, protección de formularios y cabeceras. |
| [Docker](arquitecture/DOCKER.md) | Plataformas, montaje y configuración del administrador. |

Los [ADR](decisions/) registran decisiones, alternativas y consecuencias.
Los [resúmenes por versión](version/) describen el alcance histórico y los
[informes](tests/README.md) conservan resultados y límites de validación.
