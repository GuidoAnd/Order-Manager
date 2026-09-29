# ADR-004 — Pruebas funcionales en móviles

## Estado
Aceptada

## Fecha
2026-09-29

## Contexto
La interfaz HTML/CSS debe permitir completar el flujo principal desde 320 px.
Las pruebas de modelos y rutas no detectan controles inaccesibles ni desbordes
que aparecen al renderizar una página en un navegador.

## Decisión
Usar pytest con Playwright y Chromium sin interfaz para probar la aplicación en
320x568, 375x667, 430x932, 768x1024 y 1366x768. En cada tamaño se recorre
la creación de jornada, alta de autor, orden con dos artículos, estadísticas,
catálogo vendido y registros. Se comprueba que el documento y los controles
queden dentro del viewport. Las tablas pueden desplazarse horizontalmente
únicamente dentro de su contenedor.

El navegador recibe las respuestas de FastAPI mediante una ruta interceptada
que llama a la aplicación ASGI en el mismo proceso. Así se prueban los
formularios reales sin abrir un puerto. El adaptador sigue internamente las
redirecciones de los formularios. Las pruebas usan archivos temporales para
las estadísticas globales y el inventario persistente, sin modificar los
datos de ejecución habituales.

Playwright se fija en `requirements-test-dev.txt`. La instalación del navegador se
realiza con `python -m playwright install --only-shell chromium`. Chromium
necesita fuentes y bibliotecas de sistema para medir y mostrar el texto.

## Motivos
- Verifica las interacciones y las dimensiones en un navegador real.
- Cubre el ancho mínimo junto con tamaños intermedios y de escritorio.
- Reutiliza pytest sin añadir otra herramienta de pruebas visuales.
- Evita exponer un servidor durante la validación.

## Alternativas consideradas
- Inspección manual: difícil de repetir con cada cambio.
- Probar solo respuestas ASGI: no mide el diseño ni la accesibilidad visual.
- Capturas como única prueba: no verifican que los botones funcionen.

## Consecuencias
- La suite requiere descargar Chromium compatible con la versión fijada.
- Los entornos mínimos deben disponer de bibliotecas y fuentes para Chromium.
- La prueba comprueba funcionalidad y geometría; no compara capturas píxel a píxel.

## Revisar cuando
- Cambien los flujos principales o el ancho mínimo soportado.
- Se incorpore una interfaz con interacciones que no cubra esta prueba.
