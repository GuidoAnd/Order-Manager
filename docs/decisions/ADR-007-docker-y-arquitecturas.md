# ADR-007 — Docker y arquitecturas de ejecución

## Estado
Aceptada

## Fecha
2026-10-14

## Contexto
El MVP necesita un empaquetado reproducible con datos independientes de la imagen.
Un cliente solicitó una variante específica para Intel Atom N270 de 32 bits.

## Decisión
Preparar una imagen moderna para linux/amd64 y linux/arm64, con builder/runtime,
venv, dependencias fijadas y usuario sin privilegios. La distribución conjunta
usa un índice multiarquitectura: cada plataforma tiene sus propios binarios.
La variante linux/386 para Atom se mantiene fuera del repositorio de aplicación.

Fijar Python 3.13.16 sobre Alpine 3.23 mediante versión y digest del índice oficial.
Se conserva Python 3.13, ya utilizado, y se actualiza únicamente el parche del
contenedor. Alpine 3.23 es la rama estable anterior soportada. Las dependencias
de requirements.txt conservan sus versiones. El entorno local sigue en Python
3.13.5; sus pruebas no acreditan la ejecución del runtime de la imagen.

Usar ruedas binarias en amd64/arm64. En i386, compilar pydantic-core y MarkupSafe
con Rust/C y herramientas fijadas, sin instrucciones de CPU nativa. Mantener
compiladores fuera del runtime. UID/GID y rutas de montaje son configurables;
el arranque exige un DATA_DIR absoluto, existente y escribible.

Compose prepara una instancia, un worker, raíz de solo lectura, capacidades
retiradas y puerto del host en loopback por defecto. La actualización de ADR-005
permite configurar la publicación mediante APP_BIND_HOST para acceso LAN temporal.
Construir y ejecutar las imágenes
corresponde al usuario y queda fuera de las comprobaciones de esta etapa.

## Motivos
- Separar datos e imagen permite reemplazar el contenedor conservando el estado.
- Las etapas de construcción evitan distribuir herramientas de compilación.
- El contexto permitido contiene únicamente el runtime, sus plantillas y estáticos.
- El índice multiarquitectura permite seleccionar la variante correcta.

## Alternativas consideradas
- Una única imagen amd64: excluye equipos ARM.
- Una imagen universal con binarios mezclados: no corresponde al modelo Docker.
- Compiladores dentro del runtime: aumenta tamaño y superficie de ataque.

## Consecuencias
- Compartir DATA_DIR no habilita varios escritores; continúa una instancia y un worker.
- El administrador prepara permisos y montaje; el arranque no cambia propietarios.
- No se incluyen documentos privados, pruebas, credenciales ni datos en el contexto.
- La variante Atom requiere compilación y un sistema anfitrión compatible con Docker.
- Las versiones y digests se actualizan expresamente, tras revisar compatibilidad.

## Revisar cuando
- Se incorporen otras plataformas, varios escritores o exposición en red.
- Cambie el soporte de Python/Alpine o aparezcan incompatibilidades de compilación.

Referencias: [Docker multiarquitectura](https://docs.docker.com/build/building/multi-platform/),
[soporte Alpine](https://alpinelinux.org/releases/) y
[versiones Python](https://devguide.python.org/versions/).
