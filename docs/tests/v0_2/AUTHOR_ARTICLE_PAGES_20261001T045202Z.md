# Artículos por autor en Jornada — v0.2

Fecha UTC: **2026-10-01T04:52:02Z**.
Resultado: **PASS**.

## Alcance

- Cinco artículos por página en «Resultados por autor», sin cambiar el tamaño
  de la tabla ni los totales completos.
- Anterior/Siguiente y páginas independientes para cada autor.
- Cero, cinco, seis y once artículos; recorrido sin omisiones ni duplicados.
- Páginas inválidas o fuera de rango ajustadas; estado vacío tras borrar ventas.
- Conservación de unidades, importes, promedios, acumulados y datos de jornada.
- Navegación funcional, botones de al menos 44 px y colores distintos en
  320x568, 375x667, 430x932, 768x1024 y 1366x768.

## Resultados

Pruebas específicas: **11 PASS en 12,07 s**.
Suite completa: **107 PASS en 117,37 s** (72 unitarias/integrales y
35 de navegador). git diff --check: PASS.

## Reproducción

Con requirements-test-dev.txt y Chromium de Playwright disponibles:

```bash
python -m pytest -q -p no:cacheprovider --tb=short
```

## Limitaciones

Chromium con viewports emulados; no se probaron dispositivos físicos ni otros
motores. Las tablas conservan el desplazamiento horizontal dentro de su
contenedor cuando resulta necesario en móvil.
