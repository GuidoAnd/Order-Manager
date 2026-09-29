# ADR-003 — Exportación CSV

## Estado
Aceptada

## Fecha
2026-09-29

## Contexto
La aplicación ya exporta JSON, pero todavía no necesita
consultas relacionales ni persistencia compleja.

## Decisión
En v0.2 se exportará un CSV de ventas por artículo junto con el JSON al cerrar
la jornada, antes de agregar una base de datos SQL. El CSV reunirá las unidades
vendidas por todos los autores de esa jornada, sin separarlas por autor. Una
línea de orden con cantidad 3 aportará tres unidades al artículo correspondiente.
Las columnas de artículos se definirán según los artículos facturados en la
jornada, incluidos los agregados durante ella.

El botón de confirmación del cierre indicará expresamente que contabiliza las
ventas y descarga JSON y CSV. Ambos archivos corresponderán a la misma jornada
y al mismo estado de sus órdenes en el momento del cierre.

## Motivos
- Permite validar el modelo de datos.
- Facilita análisis externo.
- Mantiene baja la complejidad.
- Evita introducir una base de datos antes de necesitarla.

## Alternativas consideradas
- Introducir MariaDB inmediatamente.
- Mantener únicamente JSON.

## Consecuencias
--Positivas:
- Menor complejidad operativa.
- Formato portable.
- Ayuda a definir entidades y relaciones.

--Negativas:
- CSV no sirve bien para consultas complejas.
- Puede haber duplicación de información.

## Revisar cuando
- Se necesiten consultas históricas.
- Aumente el volumen.
- Sea necesaria persistencia multi-sesión.
