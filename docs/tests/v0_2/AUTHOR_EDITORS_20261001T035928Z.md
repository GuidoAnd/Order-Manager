# Autores desplegables — v0.2

Fecha UTC: **2026-10-01T03:59:28Z**.
Resultado: **PASS**.

## Alcance

- Nombres visibles con los formularios cerrados.
- Agregar autor: apertura, alta, campo limpio tras guardar y cancelación.
- Editar autores: renombrado, cancelación y eliminación sin órdenes.
- Renombrar conserva identificador y órdenes; eliminar autores con órdenes
  permanece bloqueado.
- Nombres vacíos o duplicados mantienen abierto el formulario y conservan
  el texto ingresado.
- Teclado, controles de al menos 44 px, colores diferenciados y ausencia de
  desborde en 320x568, 375x667, 430x932, 768x1024 y 1366x768.

## Resultados

Primera ejecución específica: 5 PASS y 5 FAIL por una comprobación que buscaba
botones ocultos mediante roles accesibles, que Playwright excluye por defecto.
Se corrigió el selector de la prueba; segunda ejecución: **10 PASS en 13,48 s**.

Suite completa: **84 PASS en 91,08 s** (59 unitarias/integrales y 25 de navegador).
Incluye las diez pruebas nuevas de autores y los cinco flujos principales
adaptados para abrir el formulario de alta. git diff --check: PASS.

## Reproducción

Con las dependencias de requirements-test-dev.txt y Chromium de Playwright:

```bash
python -m pytest -q -p no:cacheprovider --tb=short
```

## Limitaciones

Chromium con viewports emulados; no se probaron dispositivos físicos ni otros
motores de navegador.
