"""Interfaz HTML sencilla, renderizada en el servidor."""

from __future__ import annotations

from hashlib import sha256
from html import escape
from pathlib import Path
import json
import re
from urllib.parse import urlencode

from .article_search import ArticleSearch, article_identity, searchable
from .store import DomainError, Store, summary


STYLESHEET = Path(__file__).resolve().parent.parent / "static" / "styles.css"

def h(value: object) -> str:
    return escape(str(value), quote=True)


def article_statistics_label(key: str) -> str:
    parts = key.split(" / ")
    if len(parts) != 3:
        return key
    names = [re.sub(r"\\([\\/])", r"\1", part) for part in parts]
    return " / ".join(
        json.dumps(name, ensure_ascii=False) if " / " in name else name
        for name in names
    )


def article_statistics_name(key: str) -> str:
    """Obtiene el nombre conservando barras y caracteres originales."""
    return re.sub(r"\\([\\/])", r"\1", key.split(" / ")[-1])


def export_url(journey_id: str) -> str:
    return "/api/exports/last?" + urlencode({"journey_id": journey_id})


def stylesheet_url() -> str:
    """Cambia la URL al cambiar el CSS para evitar reutilizar una copia antigua."""
    version = sha256(STYLESHEET.read_bytes()).hexdigest()[:16]
    return "/static/styles.css?" + urlencode({"v": version})


def layout(title: str, content: str, head: str = "") -> str:
    return f"""<!doctype html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{h(title)} · Order Manager</title>
    <link rel="stylesheet" href="{h(stylesheet_url())}">
    {head}
</head>
<body>
    <header class="top">
        <a class="brand" href="/">Order Manager <small>v0.2 en desarrollo</small></a>
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
    <footer>Order Manager · v0.2 en desarrollo</footer>
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
        journey_stats = summary(journey)
        active = (
            f'<p>Jornada activa: <strong>{h(journey["title"])}</strong></p>'
            + metrics(journey_stats)
        )
        authors = "\n".join(
            f'<div class="author-summary"><h3>{h(author["name"])}</h3>'
            f'{metrics(journey_stats["by_author"][author["id"]])}</div>'
            for author in journey["authors"]
        ) or "<p>Aún no hay autores.</p>"
    else:
        active = '<p>No hay una jornada activa. <a href="/jornada">Crear jornada</a>.</p>'
        authors = "<p>No hay una jornada activa.</p>"

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
        <h2>Resultados por autor</h2>
        {authors}
    </section>
    <section class="panel">
        <h2>Acumulado global</h2>
        {metrics(globals_, True)}
        <h3>Ventas por categoría</h3>
        <ul>{categories}</ul>
    </section>"""
    return layout("Dashboard", body)


def _author_row(author: dict, values: dict) -> str:
    name = values.get("name", "") if values.get("author_id") == author["id"] else author["name"]
    return f"""<li class="author-item">
        <form method="post" action="/ui/journey">
            <input type="hidden" name="author_id" value="{h(author['id'])}">
            <label>Nombre del autor
                <input name="name" value="{h(name)}" required autocomplete="off">
            </label>
            <div class="actions">
                <button name="action" value="rename_author">Guardar nombre</button>
                <button class="danger" name="action" value="delete_author"
                        formnovalidate>Eliminar</button>
            </div>
        </form>
    </li>"""


def _author_results(author: dict, orders: list[dict], stats: dict) -> str:
    running_total = 0
    rows = []
    for order in orders:
        running_total += order["total"]
        details = "<br>".join(
            f'{h(line["name"])} × {h(line["quantity"])} '
            f'({h(line["subtotal"])})'
            for line in order["lines"]
        )
        rows.append(
            f'<tr><td>#{h(order["number"])}</td><td>{details}</td>'
            f'<td>{h(order["total"])}</td><td>{h(running_total)}</td></tr>'
        )
    order_rows = "\n".join(rows) or (
        '<tr><td colspan="4">Este autor todavía no tiene órdenes.</td></tr>'
    )
    average = f"{stats['average']:.2f}"
    article_rows = "\n".join(
        f'<tr><td>{h(article_statistics_name(name))}</td><td>{h(totals["units"])}</td>'
        f'<td>{h(totals["revenue"])}</td></tr>'
        for name, totals in sorted(
            stats["by_article"].items(),
            key=lambda item: (-item[1]["units"], item[0].casefold()),
        )
    ) or '<tr><td colspan="3">Sin artículos facturados.</td></tr>'
    return f"""<div class="author-summary">
        <h3>{h(author['name'])}</h3>
        {metrics(stats)}
        <p>Promedio por orden: {h(average)}</p>
        <div class="table-wrap">
            <table>
                <thead><tr>
                    <th>Orden</th><th>Artículos facturados</th>
                    <th>Total de la orden</th><th>Acumulado del autor</th>
                </tr></thead>
                <tbody>{order_rows}</tbody>
            </table>
        </div>
        <h4>Artículos facturados por este autor</h4>
        <div class="table-wrap">
            <table>
                <thead><tr>
                    <th>Artículo</th><th>Unidades</th><th>Importe</th>
                </tr></thead>
                <tbody>{article_rows}</tbody>
            </table>
        </div>
    </div>"""


def journey_page(
    store: Store, error: str = "", rename_title: str | None = None,
    author_values: dict | None = None,
) -> str:
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

    author_values = author_values or {}
    author_action = author_values.get("action")
    add_open = " open" if author_action == "add_author" else ""
    edit_open = " open" if author_action in {"rename_author", "delete_author"} else ""
    add_name = author_values.get("name", "") if author_action == "add_author" else ""
    author_names = "\n".join(
        f"<li>{h(author['name'])}</li>" for author in journey["authors"]
    ) or "<li>Aún no hay autores.</li>"
    authors = "\n".join(
        _author_row(author, author_values) for author in journey["authors"]
    ) or "<li>Aún no hay autores.</li>"
    stats = summary(journey)
    author_results = "\n".join(
        _author_results(
            author,
            sorted(
                (order for order in journey["orders"]
                 if order["author_id"] == author["id"]),
                key=lambda order: order["number"],
            ),
            stats["by_author"][author["id"]],
        )
        for author in journey["authors"]
    ) or "<p>Aún no hay autores.</p>"

    editor_open = " open" if rename_title is not None else ""
    title_value = journey["title"] if rename_title is None else rename_title
    body = f"""<section class="panel">
        <details class="journey-name-editor"{editor_open}>
            <summary aria-label="Editar nombre">
                <h2>{h(journey['title'])}</h2>
                <span class="button quiet">Editar nombre</span>
            </summary>
            <form method="post" action="/ui/journey">
                <label>Nombre de la jornada
                    <input name="title" value="{h(title_value)}" required maxlength="120">
                </label>
                <div class="actions">
                    <button name="action" value="rename">Guardar</button>
                    <a class="button quiet" href="/jornada">Cancelar</a>
                </div>
            </form>
        </details>
        <p>Abierta: {h(journey['opened_at'])}</p>
    </section>
    <section class="panel">
        <h2>Autores</h2>
        <div class="authors-layout">
            <details class="author-add author-disclosure"{add_open}>
                <summary class="button add-article">Agregar autor</summary>
                <form method="post" action="/ui/journey">
                    <label>Nombre del autor
                        <input name="name" value="{h(add_name)}" required autocomplete="off">
                    </label>
                    <div class="actions">
                        <button name="action" value="add_author">Guardar autor</button>
                        <a class="button quiet" href="/jornada">Cancelar</a>
                    </div>
                </form>
            </details>
            <div class="authors-registered">
                <h3>Autores dados de alta</h3>
                <ul class="list author-names">{author_names}</ul>
                <details class="author-editor author-disclosure"{edit_open}>
                    <summary class="button quiet">Editar autores</summary>
                    <ul class="list">{authors}</ul>
                    <a class="button quiet" href="/jornada">Cancelar</a>
                </details>
            </div>
        </div>
    </section>
    <section class="panel">
        <h2>Resultados por autor</h2>
        {author_results}
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
    price = article["unit_price"]
    price_label = "precio a completar" if price is None else str(price)
    temporary_label = " · de esta jornada" if article.get("temporary") else ""
    return (
        f'<option value="{h(article["id"])}"{selected}>'
        f'{h(article["name"])} · {h(price_label)}{h(temporary_label)}</option>'
    )


def _catalog_options(catalog: list[dict], selected_id: str) -> str:
    options = []
    current_group = None
    for article in sorted(
        catalog,
        key=lambda item: (
            item["category"].casefold(),
            item["subcategory"].casefold(),
            item["name"].casefold(),
        ),
    ):
        group = (article["category"], article["subcategory"])
        if group != current_group:
            if current_group is not None:
                options.append("</optgroup>")
            options.append(f'<optgroup label="{h(" / ".join(group))}">')
            current_group = group
        options.append(_catalog_option(article, selected_id))
    if current_group is not None:
        options.append("</optgroup>")
    return "\n".join(options)


def _taxonomy_fields(index: int | str, row: dict, inventory: dict) -> str:
    category_options = []
    subcategory_fields = []
    for position, category in enumerate(inventory["categories"]):
        selected = " selected" if row.get("category") == category["name"] else ""
        category_options.append(
            f'<option value="{h(category["name"])}"{selected}>'
            f'{h(category["name"])}</option>'
        )
        current = row.get("subcategories", {}).get(str(position), "")
        if not current and selected:
            current = row.get("subcategory", "")
        options = []
        for subcategory in inventory["subcategories"]:
            if subcategory["category_id"] != category["id"]:
                continue
            checked = " selected" if current == subcategory["name"] else ""
            options.append(
                f'<option value="{h(subcategory["name"])}"{checked}>'
                f'{h(subcategory["name"])}</option>'
            )
        subcategory_fields.append(f"""<label class="subcategory-choice subcategory-{position}">
            Subcategoría
            <select name="subcategory_{index}_{position}">
                <option value="">Seleccionar subcategoría</option>
                {''.join(options)}
            </select>
        </label>""")
    return f"""<label>Categoría
        <select class="category-select" name="category_{index}">
            <option value="">Seleccionar categoría</option>
            {''.join(category_options)}
        </select>
    </label>
    {''.join(subcategory_fields)}"""


def _new_article_fields(index: int, row: dict, inventory: dict) -> str:
    price = row.get("new_unit_price", row.get("unit_price", "") if row.get("name") else "")
    return f"""<div class="new-article-fields taxonomy-fields">
        <label>Nombre
            <input name="name_{index}" value="{h(row.get('name', ''))}">
        </label>
        {_taxonomy_fields(index, row, inventory)}
        <label>Precio unitario del producto nuevo
            <input name="new_unit_price_{index}" type="number" min="0" step="1"
                   value="{h(price)}">
        </label>
    </div>"""


def _subcategory_styles(inventory: dict) -> str:
    rules = "\n".join(
        f'.taxonomy-fields:has(.category-select option:nth-child({position + 2}):checked) '
        f'.subcategory-{position} {{ display: block; }}'
        for position in range(len(inventory["categories"]))
    )
    return f"<style>\n{rules}\n</style>"


def _order_line(index: int, row: dict, catalog: list[dict], inventory: dict) -> str:
    def value(key: str) -> str:
        return h(row.get(key, ""))

    catalog_options = _catalog_options(catalog, row.get("catalog_id", ""))
    quantity = value("quantity") or "1"
    source = row.get("source", "new" if row.get("name") else "inventory")
    inventory_checked = " checked" if source == "inventory" else ""
    new_checked = " checked" if source == "new" else ""
    inventory_price = value("unit_price") if source == "inventory" or "source" in row else ""
    return f"""<fieldset class="order-line">
        <legend>Artículo {index + 1}</legend>
        <label>Cantidad
            <input name="quantity_{index}" type="number" min="1" step="1"
                   value="{quantity}" required>
        </label>
        <div class="article-source">
            <input id="inventory_{index}" name="source_{index}" type="radio"
                   value="inventory"{inventory_checked}>
            <label for="inventory_{index}">Del inventario</label>
            <input id="new_{index}" name="source_{index}" type="radio"
                   value="new"{new_checked}>
            <label for="new_{index}">Nuevo producto</label>
            <div class="inventory-fields">
                <label>Elegir del inventario
                    <select name="catalog_id_{index}">
                        <option value="">Seleccionar artículo</option>
                        {catalog_options}
                    </select>
                </label>
                <label>Precio unitario si falta en el inventario
                    <input name="unit_price_{index}" type="number" min="0" step="1"
                           value="{inventory_price}">
                </label>
            </div>
            {_new_article_fields(index, row, inventory)}
        </div>
        <div class="order-line-actions">
            <button class="danger order-secondary" name="action" value="remove_{index}">
                Quitar artículo
            </button>
        </div>
    </fieldset>"""


def _order_row(
    order: dict, authors: dict[str, str], page: int, article_id: str, query: str,
) -> str:
    details = ", ".join(
        f'{line["name"]} × {line["quantity"]}'
        for line in order["lines"]
    )
    author_name = authors.get(order["author_id"], "—")
    return f"""<tr>
        <td data-label="Número">#{h(order['number'])}</td>
        <td data-label="Autor">{h(author_name)}</td>
        <td data-label="Artículos">{h(details)}</td>
        <td data-label="Total">{h(order['total'])}</td>
        <td data-label="Acciones">
            <div class="row-actions">
                <form method="get" action="/ordenes#order-editor">
                    {_order_list_fields(page, article_id, query)}
                    <input type="hidden" name="edit" value="{h(order['id'])}">
                    <button type="submit">Editar</button>
                </form>
                <form method="post" action="/ui/orders/delete">
                    {_order_list_fields(page, article_id, query)}
                    <input type="hidden" name="order_id" value="{h(order['id'])}">
                    <button class="danger" type="submit">Eliminar</button>
                </form>
            </div>
        </td>
    </tr>"""


def _order_list_fields(page: int, article_id: str, query: str) -> str:
    return (
        f'<input type="hidden" name="page" value="{h(page)}">'
        f'<input type="hidden" name="article" value="{h(article_id)}">'
        f'<input type="hidden" name="q" value="{h(query)}">'
    )


def orders_url(page: int = 1, article_id: str = "", query: str = "") -> str:
    return "/ordenes?" + urlencode({"page": page, "article": article_id, "q": query})


def _order_results(
    orders: list[dict], authors: list[dict], page: int, article_id: str,
    query: str, size: int,
) -> str:
    total = len(orders)
    pages = max(1, (total + size - 1) // size)
    page = min(max(1, page), pages)
    selected = orders[(page - 1) * size:page * size]
    names = {author["id"]: author["name"] for author in authors}
    sections = []
    for author in authors:
        author_orders = [order for order in selected if order["author_id"] == author["id"]]
        if not author_orders:
            continue
        rows = "\n".join(
            _order_row(order, names, page, article_id, query) for order in author_orders
        )
        sections.append(f"""<div class="author-summary">
            <h3>{h(author['name'])}</h3>
            <div class="table-wrap responsive-table">
                <table>
                    <thead><tr>
                        <th>Número</th><th>Autor</th><th>Artículos</th>
                        <th>Total</th><th>Acciones</th>
                    </tr></thead>
                    <tbody>{rows}</tbody>
                </table>
            </div>
        </div>""")
    content = "\n".join(sections) or (
        "<p>No hay órdenes que coincidan con la búsqueda.</p>" if query.strip()
        else "<p>No hay órdenes que usen este artículo.</p>" if article_id
        else "<p>Aún no hay órdenes.</p>"
    )
    links = []
    if page > 1:
        links.append(
            f'<a class="button" href="{h(orders_url(page - 1, article_id, query))}#order-results">Anterior</a>'
        )
    if page < pages:
        links.append(
            f'<a class="button quiet" href="{h(orders_url(page + 1, article_id, query))}#order-results">Siguiente</a>'
        )
    label = "orden" if total == 1 else "órdenes"
    return f"""<div class="order-page-size order-page-{size}">
        <p role="status">{total} {label} · Página {page} de {pages}</p>
        {content}
        <nav class="pagination" aria-label="Páginas de órdenes">{''.join(links)}</nav>
    </div>"""


def _order_page_styles() -> str:
    """Mantiene una sola página visible, incluso con estilos externos antiguos."""
    return """<style>
        #order-results .order-page-size {
            display: none;
        }
        #order-results .order-page-2 {
            display: block;
        }
        @media (min-width: 375px) {
            #order-results .order-page-2 {
                display: none;
            }
            #order-results .order-page-3 {
                display: block;
            }
        }
        @media (min-width: 651px) {
            #order-results .order-page-3 {
                display: none;
            }
            #order-results .order-page-4 {
                display: block;
            }
        }
        @media (min-width: 1024px) {
            #order-results .order-page-4 {
                display: none;
            }
            #order-results .order-page-5 {
                display: block;
            }
        }
    </style>"""


def orders_page(
    store: Store,
    rows: list[dict] | None = None,
    author_id: str = "",
    edit_id: str = "",
    error: str = "",
    article_id: str = "",
    page: int = 1,
    query: str = "",
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
    available_articles = store.get_available_articles()
    inventory = store.get_inventory()
    line_cards = "\n".join(
        _order_line(index, row, available_articles, inventory)
        for index, row in enumerate(rows)
    )
    visible_orders = journey["orders"]
    filter_notice = ""
    if article_id:
        article = next(
            (item for item in available_articles if item["id"] == article_id), None,
        )
        visible_orders = [
            order for order in visible_orders
            if article and any(
                article_identity(line) == article_identity(article)
                for line in order["lines"]
            )
        ]
        description = (
            f'Órdenes que usan <strong>{h(article["name"])}</strong>.'
            if article else "El artículo ya no está presente en las órdenes vigentes."
        )
        back = ArticleSearch(query=article["name"] if article else "").url()
        filter_notice = (
            f'<p>{description}</p><div class="actions">'
            f'<a class="button" href="{h(back)}#article-results">Volver a Artículos</a>'
            '<a class="button quiet" href="/ordenes">Ver todas las órdenes</a></div>'
        )
    search_query = searchable(query.strip())
    if search_query:
        names = {author["id"]: author["name"] for author in journey["authors"]}
        number = search_query.removeprefix("#").strip()
        visible_orders = [
            order for order in visible_orders
            if (
                str(order["number"]) == number if number.isdecimal()
                else search_query in searchable(names.get(order["author_id"], ""))
            )
        ]
    visible_orders = sorted(visible_orders, key=lambda order: order["number"])
    grouped_orders = "\n".join(
        _order_results(visible_orders, journey["authors"], page, article_id, query, size)
        for size in (5, 4, 3, 2)
    )
    form_title = "Editar orden" if selected_order else "Crear orden"

    body = f"""<section class="panel">
        <h2>Órdenes por autor</h2>
        {filter_notice}
        <form class="order-search" method="get" action="/ordenes#order-results">
            <input type="hidden" name="article" value="{h(article_id)}">
            <label>Buscar por número o autor
                <input type="search" name="q" value="{h(query)}"
                       placeholder="90 o nombre del autor">
            </label>
            <div class="actions">
                <button type="submit">Buscar</button>
                <a class="button quiet" href="{h(orders_url(article_id=article_id))}#order-results">
                    Limpiar búsqueda
                </a>
            </div>
        </form>
        <div id="order-results">{grouped_orders}</div>
    </section>
    <section class="panel" id="order-editor">
        <h2>{form_title}</h2>
        <p>Selecciona artículos del inventario y agrega varias líneas, por ejemplo
           Café × 3. Completa el precio cuando el artículo no lo tenga definido.
           El total se calcula al guardar.</p>
        <form method="post" action="/ui/orders/form" novalidate>
            {_order_list_fields(page, article_id, query)}
            <input type="hidden" name="count" value="{len(rows)}">
            <input type="hidden" name="order_id" value="{h(edit_id)}">
            <label>Autor
                <select name="author_id" required>
                    <option value="">Seleccionar autor</option>
                    {author_options}
                </select>
            </label>
            {line_cards}
            <div class="actions order-actions">
                <button class="add-article order-secondary" name="action" value="add">
                    Agregar artículo
                </button>
                <button class="save-order" name="action" value="save">Guardar orden</button>
            </div>
        </form>
    </section>"""
    return layout(
        "Órdenes", alert(error) + body,
        _subcategory_styles(inventory) + _order_page_styles(),
    )


def _search_fields(search: ArticleSearch, *, post: bool = False, page: int | None = None) -> str:
    return "\n".join(
        f'<input type="hidden" name="{h(key)}" value="{h(value)}">'
        for key, value in search.fields(post=post, page=page).items()
    )


def _article_row(article: dict, search: ArticleSearch, page: int) -> str:
    price = article["unit_price"]
    price_label = "Pendiente" if price is None else str(price)
    return f"""<tr>
        <td data-label="Nombre">{h(article['name'])}</td>
        <td data-label="Categoría">{h(article['category'])}</td>
        <td data-label="Subcategoría">{h(article['subcategory'])}</td>
        <td data-label="Precio">{h(price_label)}</td>
        <td data-label="Acciones">
            <div class="row-actions">
                <form method="get" action="/articulos#article-editor">
                    {_search_fields(search, page=page)}
                    <input type="hidden" name="edit" value="{h(article['id'])}">
                    <button type="submit">Editar</button>
                </form>
                <form method="post" action="/ui/articles">
                    {_search_fields(search, post=True, page=page)}
                    <input type="hidden" name="article_id" value="{h(article['id'])}">
                    <button class="danger" name="action" value="delete">Eliminar</button>
                </form>
            </div>
        </td>
    </tr>"""


def _temporary_article_row(article: dict) -> str:
    orders_url = "/ordenes?" + urlencode({"article": article["id"]})
    return f"""<tr>
        <td data-label="Nombre">{h(article['name'])}</td>
        <td data-label="Categoría">{h(article['category'])}</td>
        <td data-label="Subcategoría">{h(article['subcategory'])}</td>
        <td data-label="Precio">{h(article['unit_price'])}</td>
        <td data-label="Acciones">
            <p>Temporal de esta jornada</p>
            <a class="button" href="{h(orders_url)}">Ver órdenes que lo usan</a>
        </td>
    </tr>"""


def _article_page_styles() -> str:
    """Entrega con el HTML las reglas que mantienen una sola lista visible."""
    return """<style>
        #available-articles .article-page-size {
            display: none;
        }
        #available-articles .article-page-2 {
            display: block;
        }
        @media (min-width: 375px) {
            #available-articles .article-page-2 {
                display: none;
            }
            #available-articles .article-page-3 {
                display: block;
            }
        }
        @media (min-width: 651px) {
            #available-articles .article-page-3 {
                display: none;
            }
            #available-articles .article-page-4 {
                display: block;
            }
        }
        @media (min-width: 1024px) {
            #available-articles .article-page-4 {
                display: none;
            }
            #available-articles .article-page-5 {
                display: block;
            }
        }
    </style>"""


def _article_results(available: list[dict], search: ArticleSearch, page_size: int) -> str:
    articles, total, page, pages = search.results(available, page_size=page_size)
    rows = "\n".join(
        _temporary_article_row(article) if article.get("temporary")
        else _article_row(article, search, page)
        for article in articles
    ) or '<tr><td colspan="5">No hay artículos que coincidan con la búsqueda.</td></tr>'
    links = []
    if page > 1:
        links.append(f'<a class="button" href="{h(search.url(page=page - 1))}#article-results">Anterior</a>')
    if page < pages:
        links.append(f'<a class="button quiet" href="{h(search.url(page=page + 1))}#article-results">Siguiente</a>')
    result_label = "resultado" if total == 1 else "resultados"
    return f"""<div class="article-page-size article-page-{page_size}">
        <p role="status">{total} {result_label} · Página {page} de {pages}</p>
        <div class="table-wrap responsive-table">
            <table>
                <thead><tr><th>Nombre</th><th>Categoría</th><th>Subcategoría</th>
                    <th>Precio</th><th>Acciones</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
        <nav class="pagination" aria-label="Páginas de artículos">{''.join(links)}</nav>
    </div>"""


def _article_browser(store: Store, search: ArticleSearch) -> str:
    inventory = store.get_inventory()
    categories = "\n".join(
        f'<option value="{h(category["name"])}'
        f'"{" selected" if category["name"] == search.category else ""}>'
        f'{h(category["name"])}</option>'
        for category in inventory["categories"]
    )
    subcategories = []
    for category in inventory["categories"]:
        if search.category and category["name"] != search.category:
            continue
        options = "\n".join(
            f'<option value="{h(item["name"])}'
            f'"{" selected" if item["name"] == search.subcategory else ""}>'
            f'{h(item["name"])}</option>'
            for item in inventory["subcategories"] if item["category_id"] == category["id"]
        )
        subcategories.append(f'<optgroup label="{h(category["name"])}">{options}</optgroup>')
    available = store.get_available_articles()
    results = "\n".join(_article_results(available, search, size) for size in (5, 4, 3, 2))
    return f"""<form class="article-search" method="get" action="/articulos#article-results">
        <label>Buscar por nombre
            <input type="search" name="q" value="{h(search.query)}">
        </label>
        <details{' open' if search.category or search.subcategory else ''}>
            <summary>Filtros de categoría y subcategoría</summary>
            <label>Categoría
                <select name="category"><option value="">Todas</option>{categories}</select>
            </label>
            <label>Subcategoría
                <select name="subcategory"><option value="">Todas</option>
                    {''.join(subcategories)}
                </select>
            </label>
        </details>
        <div class="actions">
            <button type="submit">Buscar</button>
            <a class="button quiet" href="/articulos#article-results">Limpiar búsqueda</a>
        </div>
    </form>
    <div id="available-articles">{results}</div>"""


def articles_page(
    store: Store,
    edit_id: str = "",
    error: str = "",
    values: dict | None = None,
    search: ArticleSearch | None = None,
) -> str:
    journey = store.get_journey()
    if not journey:
        message = '<p>Primero <a href="/jornada">crea una jornada</a>.</p>'
        return layout("Artículos", alert(error) + message)

    search = search or ArticleSearch()
    current = next(
        (article for article in journey["articles"] if article["id"] == edit_id),
        {},
    )
    form_title = "Editar artículo" if current else "Agregar artículo"
    if values is not None:
        current = values
    sold_articles = summary(journey)["by_article"]
    sold_rows = "\n".join(
        f'<tr><td data-label="Artículo">{h(article_statistics_name(name))}</td>'
        f'<td data-label="Unidades vendidas">{h(totals["units"])}</td>'
        f'<td data-label="Importe">{h(totals["revenue"])}</td></tr>'
        for name, totals in sorted(
            sold_articles.items(),
            key=lambda item: (-item[1]["units"], item[0].casefold()),
        )
    )
    if not sold_rows:
        sold_rows = '<tr><td colspan="3">Todavía no hay artículos vendidos.</td></tr>'

    body = f"""<section class="panel">
        <h2>Catálogo vendido de la jornada</h2>
        <p>Unidades facturadas en las órdenes actuales, de mayor a menor.</p>
        <div class="table-wrap responsive-table" id="sold-articles">
            <table>
                <thead><tr>
                    <th>Artículo</th><th>Unidades vendidas</th><th>Importe</th>
                </tr></thead>
                <tbody>{sold_rows}</tbody>
            </table>
        </div>
    </section>
    <section class="panel" id="article-results">
        <h2>Artículos disponibles para órdenes</h2>
        <p>Los artículos guardados y los temporales de órdenes vigentes sirven
           como referencia para nuevas órdenes.</p>
        {_article_browser(store, search)}
    </section>
    <section class="panel" id="article-editor">
        <h2>{form_title}</h2>
        <form method="post" action="/ui/articles" novalidate>
            {_search_fields(search, post=True)}
            <input type="hidden" name="article_id" value="{h(edit_id)}">
            <div class="grid taxonomy-fields">
                <label>Nombre
                    <input name="name" value="{h(current.get('name', ''))}" required>
                </label>
                {_taxonomy_fields("article", current, store.get_inventory())}
                <label>Precio unitario (opcional)
                    <input name="unit_price" type="number" min="0" step="1"
                           value="{h(current.get('unit_price') if current.get('unit_price') is not None else '')}">
                </label>
            </div>
            <div class="actions">
                <button type="submit">Guardar artículo</button>
            </div>
        </form>
    </section>"""
    styles = _subcategory_styles(store.get_inventory()) + _article_page_styles()
    return layout("Artículos", alert(error) + body, styles)


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
        journey_id, _payload = store.get_last_export()
        download = (
            f'<p><a class="button" href="{h(export_url(journey_id))}">'
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
        <p>Esta lista muestra únicamente la jornada activa. Sus registros se incluyen
           en la exportación JSON al cerrarla.</p>
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
            <input type="hidden" name="journey_id" value="{h(journey['id'])}">
            <button class="{button_class}" type="submit">{h(button_label)}</button>
            <a class="button quiet" href="/jornada">Cancelar</a>
        </form>
    </section>"""
    return layout(title, body)


def closed_journey_page(journey_id: str) -> str:
    download = h(export_url(journey_id))
    body = f"""<section class="panel">
        <p>La jornada se cerró y sus ventas se contabilizaron.</p>
        <p>La descarga del JSON comenzará automáticamente.</p>
        <p>Si no comienza, <a href="{download}">descargar JSON</a>.</p>
        <iframe src="{download}" title="Descarga de la jornada" hidden></iframe>
    </section>"""
    refresh = '<meta http-equiv="refresh" content="2;url=/">'
    return layout("Jornada cerrada", body, refresh)
