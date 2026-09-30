# Búsqueda de artículos y fichas móviles — v0.2

Timestamp UTC: **2026-09-30T03:22:13Z**.

Resultado final: **PASS — 47 pruebas en 50,56 s**: 42 unitarias e integrales
y cinco casos de navegador.

## Cobertura

- Cinco artículos disponibles por página, orden estable, navegación y ajuste a la
  última página cuando el número solicitado supera los resultados.
- Búsqueda parcial por nombre sin distinguir mayúsculas ni acentos, filtros por
  categoría/subcategoría, resultados vacíos y escape del texto introducido.
- Conservación de búsqueda y filtros al editar, guardar, eliminar y mostrar errores.
  Editar el precio del catálogo conserva los totales de las órdenes existentes.
- Los temporales permiten ver sus órdenes por categoría, subcategoría y nombre,
  incluso cuando otro producto tiene el mismo nombre. Se comprueban varios autores
  y el aviso de un enlace cuyo temporal ya desapareció.
- Fichas de Artículos y Órdenes sin desborde horizontal en móvil. Se verifican
  dimensiones de celdas y contenedores, incluyendo nombres, categorías y subcategorías
  largos sin espacios. El flujo completo continúa hasta cerrar y descargar el JSON.

| Viewport | Flujo funcional | Página dentro del ancho | Fichas sin scroll lateral |
| --- | --- | --- | --- |
| 320x568 | PASS | PASS | PASS |
| 375x667 | PASS | PASS | PASS |
| 430x932 | PASS | PASS | PASS |
| 768x1024 | PASS | PASS | Presentación de tabla |
| 1366x768 | PASS | PASS | Presentación de tabla |

## Ejecución

`python -m pytest -q -p no:cacheprovider`, sin escritura de bytecode. Se usaron
las dependencias fijadas y Chromium con JavaScript desactivado. FastAPI respondió
mediante ASGI con datos temporales, sin abrir puertos.

La primera ejecución tuvo siete fallos en las pruebas: el selector de búsqueda
coincidía con campos ocultos y se esperaba una coincidencia para «café», aunque el
catálogo contiene tres. Se corrigieron los selectores y las expectativas; la
ejecución final completa obtuvo 47 PASS.

La validación corresponde a Chromium emulado; no incluye dispositivos físicos
ni otros motores de navegador.
