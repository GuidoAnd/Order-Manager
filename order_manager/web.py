"""Interfaz HTML sencilla, renderizada en el servidor."""

from __future__ import annotations

from html import escape

from .store import DomainError, Store, summary


def h(value: object) -> str:
    return escape(str(value), quote=True)


def layout(title: str, content: str, head: str = "") -> str:
    return f"""<!doctype html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{h(title)} · Order Manager</title>
    <link rel="stylesheet" href="/static/styles.css">
    {head}
</head>
<body>
    <header class="top">
        <a class="brand" href="/">Order Manager <small>v0.1</small></a>
        <nav aria-label="Secciones">
            <a href="/">Dashboard</a>
            <a href="/jornada">Jornada</a>
            <a href="/ordenes">Órdenes</a>
            <a href="/articulos">Artículos</a>
            <a href="/registros">Registros</a>
        </nav>
    </header>
    <main>
        <h1>{h(title)}</h1>
        {content}
    </main>
    <footer>Order Manager · v0.1</footer>
</body>
</html>"""


def alert(message: str) -> str:
    if not message:
        return ""
    return f'<p class="alert" role="alert">{h(message)}</p>'


def metrics(data: dict, include_journeys: bool = False) -> str:
    pairs = []
    if include_journeys:
        pairs.append(("Jornadas cerradas", data["journeys"]))
    pairs.extend(
        [
            ("Órdenes", data["orders"]),
            ("Unidades", data["units"]),
            ("Importe", data["revenue"]),
        ]
    )
    cards = "\n".join(
        f"""<div class="metric">
            <strong>{h(value)}</strong>
            <span>{h(label)}</span>
        </div>"""
        for label, value in pairs
    )
    return f'<div class="metrics">{cards}</div>'


def dashboard(store: Store) -> str:
    journey = store.get_journey()
    if journey:
        active = (
            f'<p>Jornada activa: <strong>{h(journey["title"])}</strong></p>'
            + metrics(summary(journey))
        )
    else:
        active = '<p>No hay una jornada activa. <a href="/jornada">Crear jornada</a>.</p>'

    globals_ = store.get_globals()
    categories = "\n".join(
        f'<li>{h(name)}: {h(row["units"])} unidades · '
        f'{h(row["revenue"])} de importe</li>'
        for name, row in sorted(globals_["by_category"].items())
    )
    if not categories:
        categories = "<li>Sin ventas cerradas.</li>"

    body = f"""<section class="panel">
        <h2>Jornada</h2>
        {active}
    </section>
    <section class="panel">
        <h2>Acumulado global</h2>
        {metrics(globals_, True)}
        <h3>Ventas por categoría</h3>
        <ul>{categories}</ul>
    </section>"""
    return layout("Dashboard", body)


def _author_row(author: dict) -> str:
    return f"""<li class="author-item">
        <form class="author-actions" method="post" action="/ui/journey">
            <input type="hidden" name="author_id" value="{h(author['id'])}">
            <span class="author-name">{h(author['name'])}</span>
            <button class="danger" name="action" value="delete_author">Eliminar</button>
        </form>
    </li>"""


def journey_page(store: Store, error: str = "") -> str:
    journey = store.get_journey()
    if not journey:
        body = """<section class="panel">
            <h2>Abrir jornada</h2>
            <form method="post" action="/ui/journey">
                <input type="hidden" name="action" value="create">
                <label>Nombre de la jornada
                    <input name="title" required maxlength="120"
                           placeholder="Jornada de hoy">
                </label>
                <button type="submit">Crear jornada</button>
            </form>
        </section>"""
        return layout("Jornada", alert(error) + body)

    authors = "\n".join(_author_row(author) for author in journey["authors"])
    if not authors:
        authors = "<li>Aún no hay autores.</li>"

    body = f"""<section class="panel">
        <h2>{h(journey['title'])}</h2>
        <p>Abierta: {h(journey['opened_at'])}</p>
        <form class="inline" method="post" action="/ui/journey">
            <input name="title" value="{h(journey['title'])}" required>
            <button name="action" value="rename">Renombrar jornada</button>
        </form>
    </section>
    <section class="panel">
        <h2>Autores</h2>
        <div class="authors-layout">
            <div>
                <h3>Dar de alta un autor</h3>
                <form method="post" action="/ui/journey">
                    <label>Nombre del autor
                        <input name="name" required autocomplete="off">
                    </label>
                    <button name="action" value="add_author">Guardar autor</button>
                </form>
            </div>
            <div class="authors-registered">
                <h3>Autores dados de alta</h3>
                <ul class="list">{authors}</ul>
            </div>
        </div>
    </section>
    <section class="panel">
        <h2>Finalizar jornada</h2>
        <div class="actions journey-final-actions">
            <a class="button" href="/confirmar/close">Cerrar y contabilizar ventas</a>
            <a class="button danger" href="/confirmar/discard">
                Descartar jornada sin contabilizar ventas
            </a>
        </div>
    </section>"""
    return layout("Jornada", alert(error) + body)


def _catalog_option(article: dict, selected_id: str) -> str:
    selected = " selected" if article["id"] == selected_id else ""
    return (
        f'<option value="{h(article["id"])}"{selected}>'
        f'{h(article["name"])} · {h(article["unit_price"])}</option>'
    )


def _order_line(index: int, row: dict, catalog: list[dict]) -> str:
    def value(key: str) -> str:
        return h(row.get(key, ""))

    catalog_options = "\n".join(
        _catalog_option(article, row.get("catalog_id", ""))
        for article in catalog
    )
    quantity = value("quantity") or "1"
    return f"""<fieldset>
        <legend>Artículo {index + 1}</legend>
        <label>Elegir del catálogo (opcional)
            <select name="catalog_id_{index}">
                <option value="">Artículo nuevo</option>
                {catalog_options}
            </select>
        </label>
        <div class="grid">
            <label>Nombre
                <input name="name_{index}" value="{value('name')}">
            </label>
            <label>Categoría
                <input name="category_{index}" value="{value('category')}">
            </label>
            <label>Subcategoría
                <input name="subcategory_{index}" value="{value('subcategory')}">
            </label>
            <label>Cantidad
                <input name="quantity_{index}" type="number" min="1" step="1"
                       value="{quantity}" required>
            </label>
            <label>Precio unitario
                <input name="unit_price_{index}" type="number" min="0" step="1"
                       value="{value('unit_price')}">
            </label>
        </div>
        <button class="danger" name="action" value="remove_{index}">
            Quitar artículo
        </button>
    </fieldset>"""


def _order_row(order: dict, authors: dict[str, str]) -> str:
    details = ", ".join(
        f'{line["name"]} × {line["quantity"]}'
        for line in order["lines"]
    )
    author_name = authors.get(order["author_id"], "—")
    return f"""<tr>
        <td>#{h(order['number'])}</td>
        <td>{h(author_name)}</td>
        <td>{h(details)}</td>
        <td>{h(order['total'])}</td>
        <td>
            <div class="row-actions">
                <form method="get" action="/ordenes">
                    <input type="hidden" name="edit" value="{h(order['id'])}">
                    <button type="submit">Editar</button>
                </form>
                <form method="post" action="/ui/orders/delete">
                    <input type="hidden" name="order_id" value="{h(order['id'])}">
                    <button class="danger" type="submit">Eliminar</button>
                </form>
            </div>
        </td>
    </tr>"""


def orders_page(
    store: Store,
    rows: list[dict] | None = None,
    author_id: str = "",
    edit_id: str = "",
    error: str = "",
) -> str:
    journey = store.get_journey()
    if not journey:
        message = '<p>Primero <a href="/jornada">crea una jornada</a>.</p>'
        return layout("Órdenes", alert(error) + message)

    selected_order = next(
        (order for order in journey["orders"] if order["id"] == edit_id),
        None,
    )
    if selected_order and rows is None:
        rows = selected_order["lines"]
        author_id = selected_order["author_id"]
    if rows is None:
        rows = [{}]

    author_options = "\n".join(
        f'<option value="{h(author["id"])}"'
        f'{" selected" if author["id"] == author_id else ""}>'
        f'{h(author["name"])}</option>'
        for author in journey["authors"]
    )
    line_cards = "\n".join(
        _order_line(index, row, journey["articles"])
        for index, row in enumerate(rows)
    )
    author_names = {
        author["id"]: author["name"]
        for author in journey["authors"]
    }
    order_rows = "\n".join(
        _order_row(order, author_names)
        for order in journey["orders"]
    )
    if not order_rows:
        order_rows = '<tr><td colspan="5">Sin órdenes.</td></tr>'
    form_title = "Editar orden" if selected_order else "Crear orden"

    body = f"""<section class="panel">
        <h2>Órdenes de la jornada</h2>
        <div class="table-wrap">
            <table>
                <thead><tr>
                    <th>Número</th><th>Autor</th><th>Artículos</th>
                    <th>Total</th><th>Acciones</th>
                </tr></thead>
                <tbody>{order_rows}</tbody>
            </table>
        </div>
    </section>
    <section class="panel">
        <h2>{form_title}</h2>
        <p>Agrega varias líneas. Cada línea permite una cantidad, por ejemplo Café × 3.
           El total se calcula al guardar.</p>
        <form method="post" action="/ui/orders/form">
            <input type="hidden" name="count" value="{len(rows)}">
            <input type="hidden" name="order_id" value="{h(edit_id)}">
            <label>Autor
                <select name="author_id" required>
                    <option value="">Seleccionar autor</option>
                    {author_options}
                </select>
            </label>
            {line_cards}
            <div class="actions">
                <button class="quiet" name="action" value="add">Agregar artículo</button>
                <button name="action" value="save">Guardar orden</button>
            </div>
        </form>
    </section>"""
    return layout("Órdenes", alert(error) + body)


def _article_row(article: dict) -> str:
    return f"""<tr>
        <td>{h(article['name'])}</td>
        <td>{h(article['category'])}</td>
        <td>{h(article['subcategory'])}</td>
        <td>{h(article['unit_price'])}</td>
        <td>
            <div class="row-actions">
                <form method="get" action="/articulos">
                    <input type="hidden" name="edit" value="{h(article['id'])}">
                    <button type="submit">Editar</button>
                </form>
                <form method="post" action="/ui/articles">
                    <input type="hidden" name="article_id" value="{h(article['id'])}">
                    <button class="danger" name="action" value="delete">Eliminar</button>
                </form>
            </div>
        </td>
    </tr>"""


def articles_page(store: Store, edit_id: str = "", error: str = "") -> str:
    journey = store.get_journey()
    if not journey:
        message = '<p>Primero <a href="/jornada">crea una jornada</a>.</p>'
        return layout("Artículos", alert(error) + message)

    current = next(
        (article for article in journey["articles"] if article["id"] == edit_id),
        {},
    )
    rows = "\n".join(_article_row(article) for article in journey["articles"])
    if not rows:
        rows = '<tr><td colspan="5">Sin artículos.</td></tr>'
    form_title = "Editar artículo" if current else "Agregar artículo"

    body = f"""<section class="panel">
        <h2>Catálogo de la jornada</h2>
        <p>Los artículos guardados sirven como referencia para nuevas órdenes.</p>
        <div class="table-wrap">
            <table>
                <thead><tr>
                    <th>Nombre</th><th>Categoría</th><th>Subcategoría</th>
                    <th>Precio</th><th>Acciones</th>
                </tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
    </section>
    <section class="panel">
        <h2>{form_title}</h2>
        <form method="post" action="/ui/articles">
            <input type="hidden" name="article_id" value="{h(edit_id)}">
            <div class="grid">
                <label>Nombre
                    <input name="name" value="{h(current.get('name', ''))}" required>
                </label>
                <label>Categoría
                    <input name="category" value="{h(current.get('category', ''))}" required>
                </label>
                <label>Subcategoría
                    <input name="subcategory"
                           value="{h(current.get('subcategory', ''))}" required>
                </label>
                <label>Precio unitario
                    <input name="unit_price" type="number" min="0" step="1"
                           value="{h(current.get('unit_price', ''))}" required>
                </label>
            </div>
            <button type="submit">Guardar artículo</button>
        </form>
    </section>"""
    return layout("Artículos", alert(error) + body)


def _event_row(event: dict) -> str:
    return f"""<tr>
        <td>{h(event['at'])}</td>
        <td>{h(event['action'])}</td>
        <td>{h(event['detail'])}</td>
    </tr>"""


def events_page(store: Store) -> str:
    rows = "\n".join(_event_row(event) for event in reversed(store.get_events()))
    if not rows:
        rows = '<tr><td colspan="3">Sin movimientos.</td></tr>'
    try:
        store.get_last_export()
        download = (
            '<p><a class="button" href="/api/exports/last">'
            'Descargar último JSON exportado</a></p>'
        )
    except DomainError:
        download = ""

    body = f"""<section class="panel">
        <h2>Movimientos de la jornada</h2>
        <div class="table-wrap">
            <table>
                <thead><tr><th>Fecha</th><th>Acción</th><th>Detalle</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
        <p>Los registros de la jornada se incluyen en la exportación JSON al cerrarla.
           La lista visible se pierde al reiniciar la aplicación.</p>
        {download}
    </section>"""
    return layout("Registros y exportación", body)


def confirm_page(store: Store, action: str) -> str:
    journey = store.get_journey()
    if not journey or action not in ("close", "discard"):
        message = '<p>Acción no disponible. <a href="/jornada">Volver a jornada</a>.</p>'
        return layout("Confirmar acción", message)

    closing = action == "close"
    if closing:
        title = "Cerrar y contabilizar ventas"
        effect = "Se descargará un JSON y las ventas se agregarán a las estadísticas globales."
    else:
        title = "Descartar jornada sin contabilizar ventas"
        effect = (
            "Se perderán los datos temporales de esta jornada; sus ventas no se "
            "agregarán a las estadísticas globales."
        )
    button_class = "" if closing else "danger"
    button_label = (
        "Cerrar ventas y contabilizarlas"
        if closing else f"Confirmar: {title}"
    )

    body = f"""<section class="panel">
        <p>Jornada: <strong>{h(journey['title'])}</strong>.</p>
        <p>{h(effect)}</p>
        <form method="post" action="/ui/journey">
            <input type="hidden" name="action" value="{action}">
            <input type="hidden" name="confirm" value="yes">
            <button class="{button_class}" type="submit">{h(button_label)}</button>
            <a class="button quiet" href="/jornada">Cancelar</a>
        </form>
    </section>"""
    return layout(title, body)


def closed_journey_page() -> str:
    body = """<section class="panel">
        <p>La jornada se cerró y sus ventas se contabilizaron.</p>
        <p>La descarga del JSON comenzará automáticamente.</p>
        <p>Si no comienza, <a href="/api/exports/last">descargar JSON</a>.</p>
        <iframe src="/api/exports/last" title="Descarga de la jornada" hidden></iframe>
    </section>"""
    refresh = '<meta http-equiv="refresh" content="2;url=/">'
    return layout("Jornada cerrada", body, refresh)
