# Auditoría de errores y optimización — v0.3

Creación UTC: **2026-10-14T05:44:58Z**.
Cierre de la revisión inicial UTC: **2026-10-14T13:45:07Z**.
Actualización y cierre de la ampliación UTC: **2026-10-14T14:26:59Z**.
Versión: **v0.3 en desarrollo**. Resultado final: **PASS**.

## Alcance

Revisión de persistencia y recuperación, edición de órdenes y catálogo,
navegación, validación HTTP, consultas y pruebas existentes. Las reproducciones
usan datos temporales. Se mantienen los formatos persistentes, las series
manuales, las reglas de ventas y órdenes no facturadas y las exportaciones.
Los cambios conservan el stack, las versiones y la arquitectura actuales.

## Correcciones

### 1. Editor del catálogo después de recuperar una jornada

El listado consultaba el inventario vigente y el editor consultaba los artículos
de la jornada recuperada. Un artículo cuyo precio pasó de 100 a 300 aparecía en
el editor con 100; guardar podía revertir el precio posterior. Las altas de una
jornada posterior se mostraban en el listado, pero abrían un formulario vacío.

El listado, las opciones y el editor comparten ahora una copia del inventario
vigente por petición. Se comprueba que guardar conserve los precios y nombres
actuales, las órdenes históricas y el estado después de reiniciar.

### 2. Paginación de Jornada con muchos autores

Los enlaces añadían tres parámetros por autor, incluso cuando todas sus tablas
estaban en la primera página. Con 60 autores podían superar 8 KiB y la propia
aplicación rechazaba Siguiente con `414`.

Los enlaces incluyen únicamente páginas distintas de 1. Anterior elimina el
parámetro al regresar a la primera; las selecciones de otras tablas se conservan.
Se mantiene el límite HTTP y se comprueba navegación real con 60 autores desde
320 px. La prueba de longitud usa 60 autores y una selección independiente.

### 3. Edición de referencias de catálogo que cambian de posición

La API asociaba una línea guardada a su posición. Quitar otra línea o reordenar
artículos podía tomar nombres y precios actuales en lugar de los históricos;
si el artículo ya se había eliminado, devolvía `404`.

Se reconoce la referencia original cuando aparece una sola vez en la orden
guardada y en la solicitud. Se conservan sus datos y se admiten cambios de precio
explícitos. Las referencias repetidas conservan su correspondencia por posición;
no se infiere una identidad de línea ambigua ni se cambia el contrato de la API.
Una línea duplicada adicional toma el precio vigente. Las pruebas cubren ambos
casos, reordenamiento, eliminación de otra línea y artículo retirado del catálogo.

### 4. Mensajes y formularios no disponibles

Un enlace a un artículo inexistente mostraba un formulario de alta con un ID
de edición inválido. Ahora responde `404` con un mensaje coherente. Los errores
de dominio HTML distinguen una acción no disponible de un fallo de almacenamiento;
el título de almacenamiento queda reservado a `503`.

El texto de Artículos describe el catálogo persistente de v0.3 y las altas
incorporadas al guardar órdenes.

### 5. Sincronización de la prueba de acciones por teclado

La primera suite completa obtuvo **460 PASS y 1 FAIL**: un timeout al consultar
Editar orden después de volver a la primera página. El fallo se reprodujo en
otros viewports. Una repetición diagnóstica obtuvo 14 PASS y 1 FAIL y registró
el foco en `body`, con los menús cerrados, después de enviar Enter.

La prueba espera ahora el estado de la página de destino y su carga, envía Enter
al propio control Acciones y verifica que el menú se abra. Se conserva la
activación por teclado y las comprobaciones de tamaño, colores y eliminación.
No se aumentaron timeouts ni se añadieron reintentos. La misma repetición de
tres ejecuciones por cada uno de los cinco viewports obtuvo **15 PASS en 35,97 s**.

## Optimización

- **Guardado de órdenes:** conjuntos de identidades calculados una vez por
  operación sustituyen recorridos completos del catálogo por cada línea. Las
  altas dentro del mismo guardado actualizan el conjunto y no se duplican.
  Editar una orden histórica conserva la regla de no recrear artículos eliminados.
- **Artículos:** una copia de inventario sustituye tres copias de inventario y
  una lectura adicional de artículos. La siguiente petición refleja los cambios.
- **Registros:** una lectura del historial por petición, incluso tras recuperar
  una jornada; antes se leía dos veces para preparar tabla y aviso de descarga.

Las pruebas verifican consultas y resultados, sin depender de umbrales de tiempo.
No se introduce una caché compartida ni se debilita la confirmación persistente.

## Medición local

Comparación sintética con el código previo del repositorio: catálogo de 1.000
artículos, orden de 50 líneas que usan el último artículo y tres guardados
independientes por implementación, cada uno en un directorio temporal. Se cuenta
la función de identidad y se mide el guardado completo, incluida persistencia.

| Medida | Antes | Después |
| --- | ---: | ---: |
| Cálculos de identidad por guardado | 100.000 | 1.050 |
| Mediana de guardado | 0,341 s | 0,155 s |

Los tiempos corresponden a este entorno y conjunto sintético; no son una garantía
de rendimiento en otros equipos. Los subtotales y el total fueron idénticos.

## Validación inicial

La ejecución completa final obtuvo **461 PASS en 295,83 s (4 min 55 s)**, sin
fallos. Incluye las 17 regresiones añadidas (12 de lógica/HTTP y 5 de navegador)
y la prueba existente de teclado corregida. `git diff --check` también pasó.

Las ocho regresiones iniciales fallaron con el código anterior y pasaron tras
las correcciones. Los tres casos de desplazamiento de líneas reprodujeron pérdida
de datos históricos o `404`; después pasaron junto con persistencia: **32 PASS**.
Se añadió una comprobación de líneas duplicadas para conservar precios futuros.

La validación específica de navegador obtuvo **5 PASS**, en 320×568, 375×667,
430×932, 768×1024 y 1366×768. Incluye edición de artículos posteriores al rollback,
errores y reenvío, navegación Siguiente/Anterior y ausencia de desbordamientos.
La prueba de muchos autores se concentra en el viewport mínimo; los demás
mantienen la validación funcional y adaptable con dos autores.

Comando portable de suite completa, con Chromium de Playwright disponible:

```bash
audit_data_dir="$(mktemp -d)"
DATA_DIR="$audit_data_dir" PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider --tb=short --show-capture=no --maxfail=3
```

En el entorno de revisión se usan las rutas existentes de Chromium, bibliotecas
y fuentes mediante variables de entorno. Las solicitudes pasan directamente a
ASGI y los datos son temporales. No se abren puertos ni se instalan dependencias.
Chromium emulado no equivale a pruebas en dispositivos físicos u otros motores.

## Ampliación de las correcciones

Se amplía el contrato de edición con `line_id` opcional, generado por el servidor
para líneas nuevas. Devolverlo permite reconocer cada línea repetida al reordenar
o quitar otras líneas y conservar nombre, precio y referencia de catálogo, incluso
si el artículo fue retirado. Identificadores duplicados o ajenos a la orden se
rechazan antes de confirmar cambios. Las líneas nuevas usan referencias nuevas y
el precio vigente; no reutilizan referencias reservadas por otras líneas.

Los formularios mantienen los identificadores al agregar/quitar líneas y ante
errores. Una línea guardada del catálogo mantiene su modo y referencia al editar;
si el artículo fue retirado, la opción histórica permanece disponible en ese
editor. Las órdenes anteriores sin identificador reciben una referencia estable
en el editor y solo la confirman al guardar. Las lecturas no reescriben el historial.
Los identificadores se conservan tras reinicio, cierre, exportación JSON y rollback;
los CSV agregados mantienen su formato. Los clientes antiguos siguen admitidos,
con correspondencia posicional para referencias repetidas sin identificadores:
para reordenarlas sin ambigüedad deben devolver los `line_id` de la orden.

Cuando la consulta de paginación supera 4096 caracteres, se sustituye por un token
aleatorio y el parámetro de la tabla de destino. Todas las selecciones restantes
se conservan en un estado temporal por instancia, asociado al ID de jornada.
Los enlaces de una respuesta comparten ese estado; los enlaces cortos mantienen
el formato anterior. El almacenamiento temporal tiene bloqueo, caducidad de
30 minutos, máximo 64 entradas y 32768 selecciones totales, con expulsión de los
estados menos recientemente consultados. No contiene datos de órdenes, no toca
DATA_DIR y no modifica la persistencia del negocio ni el límite HTTP de 8 KiB.

Un token caducado, expulsado, de otra jornada o perdido al reiniciar informa al
operador y restablece las páginas. Un estado individual superior al límite se
rechaza con 413 y un mensaje para restablecerlas, sin recortar selecciones.
La prueba de navegador usa 100 autores con páginas activas desde 320 px; los
nuevos enlaces permanecen por debajo de 200 caracteres y conservan la página
de otras tablas en Anterior/Siguiente. Otra prueba reconstruye 900 selecciones
mediante un solo estado, y comprueba su aislamiento, caducidad y expulsión.

La decisión autorizada se incorpora a ADR-006, arquitectura y guía de interfaz.
Durante la validación adicional se corrigieron tres errores de preparación de
pruebas (decodificación del cierre y precio inicial). Las cinco pruebas nuevas
de formulario detectaron la pérdida de la referencia de catálogo al editar,
que se corrigió conservando el modo y la opción histórica del artículo.

La prueba existente del flujo móvil se sincroniza con el origen de catálogo que
ahora conserva el editor: comprueba el radio seleccionado y valida un precio
negativo en el campo activo, manteniendo la recuperación del formulario y el
total final. La ejecución previa detectó tres timeouts porque intentaba editar
el campo de producto nuevo, oculto al conservar el origen correcto. No se
ampliaron timeouts ni se añadieron reintentos.

## Validación de la ampliación

Cierre UTC: **2026-10-14T14:26:59Z**. La suite completa final obtuvo **474 PASS en
370,25 s (6 min 10 s)**, sin fallos. Incluye **30 regresiones de esta auditoría**:
17 iniciales y 13 adicionales (7 de lógica/HTTP y 6 de navegador).
La comprobación específica del flujo principal y edición de líneas retiradas
obtuvo **10 PASS** en los cinco viewports establecidos. `git diff --check` pasó.

Las pruebas adicionales comprueban líneas repetidas con precios distintos,
reordenamiento, eliminación de líneas, referencias ajenas y duplicadas,
inserción antes de una línea identificada, órdenes antiguas sin identificadores,
reinicio, cierre, JSON y rollback. La navegación se comprueba con 900 selecciones
restauradas mediante token y con 100 autores desde 320 px, además de caducidad,
expulsión, aislamiento de jornadas y aviso sin cambios de negocio.

Los datos de prueba son temporales, con Chromium y dependencias existentes.
No se abrieron puertos ni se instalaron dependencias. La construcción y ejecución
de imágenes Docker permanecen fuera de esta validación.
