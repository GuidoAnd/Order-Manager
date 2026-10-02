# Punto de entrada ASGI en la raíz

**Fecha:** 2026-09-29 15:15:00 UTC

| Comprobación | Resultado |
| --- | --- |
| `api.app is order_manager.api.app` | PASS |
| Suite unitaria e integral relevante | PASS: 23 pruebas en 0,56 s |
| `git diff --check` | PASS |

El módulo de la raíz importa la aplicación existente y no crea otra instancia.
