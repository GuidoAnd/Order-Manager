# Edición del nombre de jornada — v0.2

Fecha UTC: **2026-10-01T03:44:49Z**.
Resultado: **PASS**.

## Alcance

- Editor cerrado por defecto, con «Editar nombre» junto al título.
- Guardar cambia el título y cierra el formulario; conserva identificador,
  apertura, autores, catálogo y órdenes.
- Cancelar no guarda; los errores conservan el texto y el editor abierto.
- Una jornada cerrada no admite renombrado ni cambios en su exportación.
- Navegador: teclado, controles de al menos 44 px, acciones de colores
  distintos y ausencia de desborde en 320x568, 375x667, 430x932,
  768x1024 y 1366x768.

## Resultados

La primera ejecución específica obtuvo 7 PASS y 1 FAIL por una expectativa
incorrecta del test: la última exportación se guarda como identificador y
contenido, no como contenido aislado. Se corrigió esa expectativa.

Suite completa posterior: **74 PASS en 77,65 s**; 54 pruebas unitarias/integrales
y 20 de navegador. Incluye 8 pruebas nuevas del editor (3 integrales y
5 de navegador), todas PASS. Revisión de espacios con git diff --check: PASS.

## Reproducción

Ejecutar pytest con las dependencias de requirements-test-dev.txt y Chromium
de Playwright disponibles:

```bash
python -m pytest -q -p no:cacheprovider --tb=short
```

## Limitaciones

Chromium con viewports emulados; no se probaron dispositivos físicos ni otros
motores de navegador.
