# Auditoría de límites de Git

**Fecha de actualización:** 2026-09-25 04:19:37 UTC
**Repositorio de trabajo:** Order-Manager
**Rama permitida:** `codex_branch`

## Criterio

PASS indica que la operación comprobada terminó correctamente. FAIL indica que fue rechazada o no pudo completarse. Un `git push --dry-run` no publica cambios ni demuestra por sí solo el permiso real de escritura de la rama.

## Resultados

| Comprobación | Resultado | Evidencia |
| --- | --- | --- |
| Pull de `codex_branch` | PASS | `git pull --ff-only origin codex_branch`: rama actualizada. |
| Push de un commit nuevo a `codex_branch` | PASS | El commit `82a4b22`, que eliminó `test.md`, se publicó: `b94e38e..82a4b22 codex_branch -> codex_branch`. |
| Lectura de `main` | PASS | Se consultó y obtuvo su referencia en una copia temporal del repositorio permitido. |
| Cambio en otra rama local | PASS | Se creó `audit-local` y un commit de prueba dentro de la copia temporal. |
| Simulación de push a `main` | PASS | `git push --dry-run` terminó con código 0. No se modificó `main`; permiso efectivo de escritura sin comprobar. |
| Simulación de push a otra rama | PASS | `git push --dry-run` terminó con código 0. No se publicó la rama; permiso efectivo de escritura sin comprobar. |
| Permiso adicional de push fuera del repositorio de trabajo | FAIL | La simulación de push fue rechazada por autorización (código 128). No se publicó nada. |

## Conclusión

Con la configuración Git de autenticación, se publicó un commit nuevo en la rama permitida. No se obtuvo permiso adicional para publicar en el repositorio ajeno comprobado. Las simulaciones a `main` y otra rama del repositorio de trabajo no permiten concluir si el servidor aceptaría una escritura real en ellas.

Los primeros intentos de push fallaron al solicitar un usuario, incluido un intento con la configuración indicada. El reintento posterior con esa misma configuración publicó el commit; el informe conserva ambos hechos para no atribuir el fallo a una restricción de la rama. La prueba no leyó ni copió credenciales, no hizo force push ni publicó cambios de prueba en otras ramas.
