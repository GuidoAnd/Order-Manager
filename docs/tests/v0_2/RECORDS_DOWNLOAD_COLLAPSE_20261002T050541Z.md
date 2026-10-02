# Descargas compactas en Registros — v0.2

Fecha UTC: **2026-10-02T05:05:41Z**. Resultado: **PASS**.

## Alcance

- «Descargar última jornada» cerrado por defecto al visitar o recargar Registros.
- Radios ocultos hasta abrir el desplegable; apertura por toque y cierre por teclado.
- Descarga desde el selector abierto sin modificar acumulados.
- Selector visible directamente después del cierre, con los cuatro formatos disponibles.
- Regresiones de exportación, confirmaciones y paginación de Registros.
- Sin desborde en 320x568, 375x667, 430x932, 768x1024 y 1366x768;
  control desplegable de al menos 44 px.

## Resultados

**64 PASS en 30.96 s:** 54 pruebas unitarias/integrales y 10 de navegador.
`git diff --check`: **PASS**.

Ejecución centrada en exportación y Registros; la suite completa de 204 pruebas
corresponde al informe anterior. Chromium emulado, sin validación en dispositivos físicos.
