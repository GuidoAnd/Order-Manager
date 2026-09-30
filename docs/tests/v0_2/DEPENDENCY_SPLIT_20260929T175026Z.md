# Separación de dependencias — 2026-09-29T17:50:26Z

| Comprobación | Resultado |
| --- | --- |
| Instalación limpia de `requirements.txt` | PASS: 13 paquetes de ejecución |
| Importación de `order_manager.api:app` en ese entorno | PASS |
| Ausencia de pytest y Playwright en el entorno de ejecución | PASS |
| `pip check` en el entorno de ejecución | PASS |
| Instalación de `requirements-test-dev.txt` sobre ese entorno | PASS |
| Suite completa desde el entorno de pruebas | PASS: 13/13 |

Las versiones fijadas no cambiaron. El archivo de pruebas incluye el de
ejecución mediante `-r requirements.txt`. Chromium y las bibliotecas de sistema
utilizadas para las pruebas móviles permanecen fuera del repositorio.
