# ADR-001 — FastAPI como servidor de la aplicación

## Estado
Aceptada

## Fecha
2026-09-29

## Contexto
El MVP necesita servir una interfaz HTML, exponer rutas JSON y validar datos
de jornadas, autores, artículos y órdenes. La misma aplicación debe poder
ejecutarse con Uvicorn y ser importada por herramientas ASGI.

## Decisión
Usar FastAPI como capa HTTP. La aplicación ASGI se define en
`order_manager/api.py`; el `api.py` de la raíz solo expone ese objeto. Las
rutas JSON usan modelos Pydantic para validar entradas. Los formularios HTML
se procesan en rutas de interfaz y se renderizan en el servidor.

## Motivos
- FastAPI encaja con el servidor ASGI y los modelos Pydantic ya usados en el
  proyecto.
- Permite mantener rutas JSON y formularios HTML en una sola aplicación.
- La validación declarativa reduce código repetido en las entradas de la API.
- La estructura actual mantiene separadas las rutas, la lógica de negocio y
  la generación del HTML.

## Alternativas consideradas
- Flask: puede servir esta interfaz y las rutas JSON, pero en este proyecto
  habría requerido definir de otra manera la validación de los cuerpos y el
  punto de entrada ASGI. No ofrece una ventaja concreta para el MVP actual.
- Un servidor propio con la biblioteca estándar: aumentaría el trabajo de
  enrutamiento, validación y manejo de respuestas.

## Consecuencias
- FastAPI, Pydantic y Uvicorn son dependencias de ejecución fijadas.
- Las rutas y el punto de entrada siguen el contrato ASGI.
- Elegir FastAPI no sustituye la validación de reglas de negocio en `Store`.

## Revisar cuando
- Cambien los requisitos de despliegue o las necesidades de la API.
- La aplicación deje de necesitar este conjunto de rutas JSON y HTML.
