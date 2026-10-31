"""Interfaz HTML sencilla, renderizada en el servidor."""

from __future__ import annotations

from collections import deque
from dataclasses import replace
from functools import wraps
from hashlib import sha256
from html import escape
from pathlib import Path
import json
import re
from urllib.parse import urlencode

from .templating import component, render
from .order_lines import line_identifier
from .order_series import serial_label

from . import journey_results, table_pages
from .article_search import ArticleSearch, article_identity, searchable
from .store import DomainError, Store, is_sale, summary
from .security import protect_forms
from .notices import CURRENT_NOTICE


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


def download_form(journey_id: str, close_id: str | None = None) -> str:
    options = (
        ("csv_summary", "CSV resumen", "Cantidades por categoría, con artículos en columnas."),
        ("csv_detail", "CSV detallado", "Una fila por artículo con unidades e importe."),
        ("json", "JSON completo", "Órdenes, registros y datos de la jornada."),
        ("zip", "Todo en ZIP", "Los dos CSV y el JSON en una sola descarga."),
    )
    close_field = f'<input type="hidden" name="close_id" value="{h(close_id)}">' if close_id else ""
    radios = "".join(
        f'<input type="radio" name="format" id="export-{value}" value="{value}"'
        + (' checked' if value == "zip" else '') + '>'
        + f'<label for="export-{value}"><strong>{label}</strong><span>{description}</span></label>'
        for value, label, description in options
    )
    return render(
        'web/download_form.html',
        journey_id=journey_id,
        close_field=close_field,
        radios=radios,
    )


def stylesheet_url() -> str:
    """Cambia la URL al cambiar el CSS para evitar reutilizar una copia antigua."""
    version = sha256(STYLESHEET.read_bytes()).hexdigest()[:16]
    return "/static/styles.css?" + urlencode({"v": version})


def layout(title: str, content: str, head: str = "", *, show_notice: bool = True) -> str:
    content = protect_forms(content)
    sections = (
        ("/", "Dashboard"),
        ("/jornada", "Jornada"),
        ("/ordenes", "Órdenes"),
        ("/articulos", "Artículos"),
        ("/registros", "Registros"),
    )
    return render(
        'web/layout.html',
        title=title,
        stylesheet_url=stylesheet_url(),
        head=head,
        sections=sections,
        content=content,
        notice=CURRENT_NOTICE.get() if show_notice else None,
    )


def alert(message: str) -> str:
    return component("alert", message)


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
    return component("metrics", pairs)


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

    body = render(
        'web/dashboard.html',
        active=active,
        authors=authors,
        metrics_globals__True=metrics(globals_, True),
        categories=categories,
    )
    return layout("Dashboard", body)


def _author_row(author: dict, values: dict) -> str:
    name = values.get("name", "") if values.get("author_id") == author["id"] else author["name"]
    return render(
        'web/author_row.html',
        author_id=author['id'],
        name=name,
    )


def journey_article_pages(values: dict) -> dict[str, int]:
    return journey_results.page_values(values, "articles")


def _author_results(author: dict, orders: list[dict], stats: dict, pages: dict) -> str:
    average = f"{stats['average']:.2f}"
    tables = journey_results.author_tables(author, orders, stats, pages, article_statistics_name)
    return render(
        'web/author_results.html',
        author_name=author['name'],
        metrics_stats=metrics(stats),
        average=average,
        tables=tables,
    )


def journey_page(
    store: Store, error: str = "", rename_title: str | None = None,
    author_values: dict | None = None,
    article_pages: dict[str, int] | None = None,
    order_pages: dict[str, int] | None = None,
    subtotal_pages: dict[str, int] | None = None,
    navigation=None,
) -> str:
    journey = store.get_journey()
    if not journey:
        body = render(
            'web/journey_open.html',
        )
        return layout("Jornada", alert(error) + body + recovery_button(store))

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
    pages = journey_results.normalize_pages(
        journey["authors"], journey["orders"], stats,
        {"articles": article_pages or {}, "orders": order_pages or {},
         "subtotals": subtotal_pages or {}},
    )
    if navigation is not None:
        pages = journey_results.NavigationPages(pages, navigation, journey["id"])
    author_results = "\n".join(
        _author_results(
            author,
            sorted(
                (order for order in journey["orders"]
                 if order["author_id"] == author["id"]),
                key=lambda order: order["number"],
            ),
            stats["by_author"][author["id"]],
            pages,
        )
        for author in journey["authors"]
    ) or "<p>Aún no hay autores.</p>"

    editor_open = " open" if rename_title is not None else ""
    title_value = journey["title"] if rename_title is None else rename_title
    body = render(
        'web/journey_active.html',
        editor_open=editor_open,
        journey_title=journey['title'],
        journey_id=journey['id'],
        title_value=title_value,
        journey_opened_at=journey['opened_at'],
        add_open=add_open,
        add_name=add_name,
        author_names=author_names,
        edit_open=edit_open,
        authors=authors,
        author_results=author_results,
    )
    return layout("Jornada", alert(error) + body + recovery_button(store), journey_results.responsive_styles())


def _taxonomy_fields(index: int | str, row: dict, inventory: dict) -> str:
    category_options = []
    subcategory_fields = []
    for position, category in enumerate(inventory["categories"]):
        selected = " selected" if row.get("category", "").casefold() == category["name"].casefold() else ""
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
            checked = " selected" if current.casefold() == subcategory["name"].casefold() else ""
            options.append(
                f'<option value="{h(subcategory["name"])}"{checked}>'
                f'{h(subcategory["name"])}</option>'
            )
        subcategory_fields.append(render(
            'web/taxonomy_fields.html',
            position=position,
            index=index,
            position_2=position,
            join_options=''.join(options),
        ))
    return render(
        'web/taxonomy_fields_2.html',
        index=index,
        join_category_options=''.join(category_options),
        join_subcategory_fields=''.join(subcategory_fields),
    )


def _new_article_fields(index: int, row: dict, inventory: dict) -> str:
    price = row.get("new_unit_price", row.get("unit_price", "") if row.get("name") else "")
    price = "" if price is None else price
    return render(
        'web/new_article_fields.html',
        index=index,
        row_get_name=row.get('name', ''),
        taxonomy_fields_index_row_inventory=_taxonomy_fields(index, row, inventory),
        index_2=index,
        price=price,
    )


def _subcategory_styles(inventory: dict) -> str:
    rules = "\n".join(
        f'.taxonomy-fields:has(.category-select option:nth-child({position + 2}):checked) '
        f'.subcategory-{position} {{ display: block; }}'
        for position in range(len(inventory["categories"]))
    )
    return render(
        'web/subcategory_styles.html',
        rules=rules,
    )


def _order_line(index: int, row: dict, catalog: list[dict], inventory: dict) -> str:
    def value(key: str) -> str:
        return h(row.get(key) if row.get(key) is not None else "")

    selected_id = row.get("catalog_id", "")
    if selected_id and row.get("line_id") and row.get("name") and not any(
        article["id"] == selected_id for article in catalog
    ):
        catalog = [*catalog, {**row, "id": selected_id}]
    selected_article = next((article for article in catalog if article["id"] == selected_id), None)
    quantity = value("quantity") or "1"
    source = row.get("source", "inventory" if selected_id else (
        "new" if row.get("name") else "inventory"
    ))
    inventory_checked = " checked" if source == "inventory" else ""
    new_checked = " checked" if source == "new" else ""
    inventory_price = value("unit_price") if source == "inventory" or "source" in row else ""
    return render(
        'web/order_line.html',
        line_id=row.get("line_id") or "",
        index_1=index + 1,
        index=index,
        quantity=quantity,
        index_2=index,
        index_3=index,
        inventory_checked=inventory_checked,
        index_4=index,
        index_5=index,
        index_6=index,
        new_checked=new_checked,
        index_7=index,
        selected_id=selected_id,
        selected_article=selected_article,
        index_9=index,
        inventory_price=inventory_price,
        new_article_fields_index_row_inventory=_new_article_fields(index, row, inventory),
        index_10=index,
    )


def _order_row(
    order: dict, authors: dict[str, str], page: int, article_id: str, query: str,
    search_by: str = "all",
) -> str:
    details = ", ".join(
        f'{line["name"]} × {line["quantity"]}'
        for line in order["lines"]
    )
    author_name = authors.get(order["author_id"], "—")
    status_label = "" if is_sale(order) else '<span class="order-state">No facturada (regalo/cancelada)</span>'
    total = h(order["total"]) if is_sale(order) else "Sin importe"
    return render(
        'web/order_row.html',
        editor_url=order_editor_url(order['id'], page, article_id, query, search_by),
        serial_label=serial_label(order),
        order_number=order['number'],
        status_label=status_label,
        author_name=author_name,
        details=details,
        total=total,
        order_number_2=order['number'],
        order_list_fields_page_article_id_query=_order_list_fields(page, article_id, query, search_by),
        order_id=order['id'],
        order_list_fields_page_article_id_query_2=_order_list_fields(page, article_id, query, search_by),
        order_id_2=order['id'],
    )


def _order_list_fields(page: int, article_id: str, query: str, search_by: str = "all") -> str:
    return component("hidden_fields", {
        "page": page, "article": article_id, "q": query, "search_by": search_by,
    })


def order_editor_url(edit_id: str = "", page: int = 1, article_id: str = "", query: str = "",
                     search_by: str = "all") -> str:
    path = f"/ordenes/{edit_id}/editar" if edit_id else "/ordenes/nueva"
    return path + "?" + urlencode({"page": page, "article": article_id, "q": query, "search_by": search_by})


def orders_url(page: int = 1, article_id: str = "", query: str = "",
               search_by: str = "all") -> str:
    return "/ordenes?" + urlencode({"page": page, "article": article_id, "q": query, "search_by": search_by})


def _shared_order_pages(orders: list[dict], authors: list[dict], size: int) -> list[list[dict]]:
    queues = {
        author["id"]: deque(sorted(
            (order for order in orders if order["author_id"] == author["id"]),
            key=lambda order: order["number"],
        )) for author in authors
    }
    pages = []
    while any(queues.values()):
        selected = [queue.popleft() for queue in queues.values() if queue]
        while len(selected) < size and any(queues.values()):
            queue = min(
                (queue for queue in queues.values() if queue),
                key=lambda queue: queue[0]["number"],
            )
            selected.append(queue.popleft())
        pages.append(sorted(selected, key=lambda order: order["number"]))
    return pages or [[]]


def _order_results(
    orders: list[dict], authors: list[dict], page: int, article_id: str,
    query: str, size: int, search_by: str = "all",
) -> str:
    total = len(orders)
    if query.strip():
        size = 5
        batches = [orders[index:index + size] for index in range(0, total, size)] or [[]]
    else:
        batches = _shared_order_pages(orders, authors, size)
    pages = len(batches)
    page = min(max(1, page), pages)
    selected = batches[page - 1]
    names = {author["id"]: author["name"] for author in authors}
    sections = []
    for author in authors:
        author_orders = [order for order in selected if order["author_id"] == author["id"]]
        if not author_orders:
            continue
        rows = "\n".join(
            _order_row(order, names, page, article_id, query, search_by) for order in author_orders
        )
        sections.append(render(
            'web/order_results.html',
            author_name=author['name'],
            rows=rows,
        ))
    content = "\n".join(sections) or (
        "<p>No hay órdenes que coincidan con la búsqueda.</p>" if query.strip()
        else "<p>No hay órdenes que usen este artículo.</p>" if article_id
        else "<p>Aún no hay órdenes.</p>"
    )
    links = []
    if page > 1:
        links.append(
            f'<a class="button" href="{h(orders_url(page - 1, article_id, query, search_by))}#order-results">Anterior</a>'
        )
    if page < pages:
        links.append(
            f'<a class="button quiet" href="{h(orders_url(page + 1, article_id, query, search_by))}#order-results">Siguiente</a>'
        )
    label = "orden" if total == 1 else "órdenes"
    return render(
        'web/order_results_2.html',
        size=size,
        total=total,
        label=label,
        page=page,
        pages=pages,
        content=content,
        join_links=''.join(links),
    )


def _order_page_styles() -> str:
    """Mantiene una sola página visible, incluso con estilos externos antiguos."""
    return render(
        'web/order_page_styles.html',
    )


def orders_page(
    store: Store,
    rows: list[dict] | None = None,
    author_id: str = "",
    edit_id: str = "",
    error: str = "",
    article_id: str = "",
    page: int = 1,
    query: str = "",
    order_status: str | None = None, *, editor: bool = False,
    series: str | None = None, serial_number: object = None,
    editor_token: str = "", editor_context: dict | None = None,
    search_by: str = "all",
) -> str:
    search_by = search_by if search_by in {"all", "author", "id", "serial"} else "all"
    journey = editor_context["journey"] if editor_context else store.get_journey()
    if not journey:
        message = '<p>Primero <a href="/jornada">crea una jornada</a>.</p>'
        return layout("Órdenes", alert(error) + message)

    editor = editor or rows is not None or bool(edit_id)
    selected_order = next(
        (order for order in journey["orders"] if order["id"] == edit_id),
        None,
    )
    if edit_id and selected_order is None:
        raise DomainError("Orden no encontrada.", 404)
    if series is None:
        series = selected_order.get("series", "") if selected_order else ""
    if serial_number is None:
        serial_number = selected_order.get("serial_number", "") if selected_order else ""
    if order_status is None:
        order_status = selected_order.get("status", "sale") if selected_order else "sale"
    sale_checked = " checked" if order_status == "sale" else ""
    not_billed_checked = " checked" if order_status == "not_billed" else ""
    if selected_order and rows is None:
        rows = [{**line, "line_id": line_identifier(selected_order["id"], index, line)}
                for index, line in enumerate(selected_order["lines"])]
        author_id = selected_order["author_id"]
    if rows is None:
        rows = [{}]

    if editor:
        author_options = component("author_options", journey["authors"], author_id)
        inventory = (editor_context["inventory"] if editor_context else
                     store.get_order_inventory(selected_order["id"] if selected_order else ""))
        available_articles = inventory["articles"]
        line_cards = "\n".join(
            _order_line(index, row, available_articles, inventory)
            for index, row in enumerate(rows)
        )
        form_title = "Editar orden" if selected_order else "Crear orden"
        body = render(
            'web/order_editor.html',
            form_title=form_title,
            cancel_url=orders_url(page, article_id, query, search_by) + "#order-results",
            editor_token=editor_token,
            list_fields=_order_list_fields(page, article_id, query, search_by),
            line_count=len(rows),
            edit_id=edit_id,
            author_options=author_options,
            sale_checked=sale_checked,
            not_billed_checked=not_billed_checked,
            line_cards=line_cards,
            series=series,
            serial_number=serial_number,
            field_errors={key: error if error.startswith(label) else ""
                          for key, label in (("series", "Serie:"), ("serial_number", "Numeración:"))},
        )
        return layout("Órdenes", alert(error) + body, _subcategory_styles(inventory))

    available_articles = store.get_available_articles()
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
        numeric = number.isascii() and number.isdecimal()
        normalized_number = number.lstrip("0") or "0"

        def matches(order):
            order_id_match = (
                (numeric and normalized_number == str(order["number"]))
                or search_query == order["id"].lower()
            )
            serial_match = numeric and normalized_number == str(order.get("serial_number"))
            author_match = search_query in searchable(names.get(order["author_id"], ""))
            if search_by == "id":
                return order_id_match
            if search_by == "serial":
                return not search_query.startswith("#") and serial_match
            if search_by == "author":
                return author_match
            return order_id_match or (not search_query.startswith("#") and (serial_match or author_match))

        visible_orders = [order for order in visible_orders if matches(order)]
    visible_orders = sorted(visible_orders, key=lambda order: order["number"])
    sizes = (5,) if search_query else (5, 4, 3, 2)
    grouped_orders = "\n".join(
        _order_results(visible_orders, journey["authors"], page, article_id, query, size, search_by)
        for size in sizes
    )
    body = render(
        'web/orders_page.html',
        filter_notice=filter_notice,
        article_id=article_id,
        query=query,
        search_by=search_by,
        orders_url_article_id_article_id=orders_url(article_id=article_id),
        grouped_orders=grouped_orders,
        new_order_url=order_editor_url('', page, article_id, query, search_by),
    )
    styles = render(
        'web/order_search_styles.html',
    ) if search_query else _order_page_styles()
    return layout("Órdenes", alert(error) + body, styles)


def _search_fields(search: ArticleSearch, *, post: bool = False, page: int | None = None) -> str:
    return component("hidden_fields", search.fields(post=post, page=page))


def _article_row(article: dict, search: ArticleSearch, page: int) -> str:
    price = article["unit_price"]
    price_label = "Pendiente" if price is None else str(price)
    return render(
        'web/article_row.html',
        article_name=article['name'],
        article_category=article['category'],
        article_subcategory=article['subcategory'],
        price_label=price_label,
        article_name_2=article['name'],
        search_fields_search_page_page=_search_fields(search, page=page),
        article_id=article['id'],
        search_fields_search_post_True_page_page=_search_fields(search, post=True, page=page),
        article_id_2=article['id'],
    )


def _temporary_article_row(article: dict) -> str:
    return render(
        'web/temporary_article_row.html',
        article_name=article['name'],
        article_category=article['category'],
        article_subcategory=article['subcategory'],
        article_unit_price=article['unit_price'],
    )


def _article_page_styles() -> str:
    """Entrega con el HTML las reglas que mantienen una sola lista visible."""
    return render(
        'web/article_page_styles.html',
    )


def _article_results(matches: list[dict], search: ArticleSearch, page_size: int) -> str:
    articles, total, page, pages = search.paginate(matches, page_size=page_size)
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
    return render(
        'web/article_results.html',
        page_size=page_size,
        total=total,
        result_label=result_label,
        page=page,
        pages=pages,
        rows=rows,
        join_links=''.join(links),
    )


def _article_browser(inventory: dict, search: ArticleSearch) -> str:
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
    matches = search.matching(inventory["articles"])
    results = "\n".join(_article_results(matches, search, size) for size in (5, 4, 3, 2))
    return render(
        'web/article_browser.html',
        search_sold_page=search.sold_page,
        search_query=search.query,
        open_if_search_category_or_search_subcategory_else=' open' if search.category or search.subcategory else '',
        categories=categories,
        join_subcategories=''.join(subcategories),
        ArticleSearch_sold_page_search_sold_page_url=ArticleSearch(sold_page=search.sold_page).url(),
        results=results,
    )


def _sold_article_row(item: tuple[str, dict]) -> str:
    name, totals = item
    return (
        f'<tr><td data-label="Artículo">{h(article_statistics_name(name))}</td>'
        f'<td data-label="Unidades vendidas">{h(totals["units"])}</td>'
        f'<td data-label="Importe">{h(totals["revenue"])}</td></tr>'
    )


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
    inventory = store.get_inventory()
    current = next(
        (article for article in inventory["articles"] if article["id"] == edit_id),
        {},
    )
    if edit_id and not current:
        raise DomainError("Artículo no encontrado.", 404)
    form_title = "Editar artículo" if current else "Agregar artículo"
    if values is not None:
        current = values
    sold_articles = sorted(
        summary(journey)["by_article"].items(),
        key=lambda item: (-item[1]["units"], item[0].casefold()),
    )
    sold_table = table_pages.table_pages(
        sold_articles, search.sold_page, ("Artículo", "Unidades vendidas", "Importe"),
        _sold_article_row, lambda page: replace(search, sold_page=page).url(),
        "artículos vendidos", "Páginas del catálogo vendido",
        "Todavía no hay artículos vendidos.", "sold-articles",
    )

    body = render(
        'web/articles_page.html',
        sold_table=sold_table,
        article_browser_store_search=_article_browser(inventory, search),
        form_title=form_title,
        search_fields_search_post_True=_search_fields(search, post=True),
        edit_id=edit_id,
        current_get_name=current.get('name', ''),
        taxonomy_fields_article_current_store_get_inventory=_taxonomy_fields('article', current, inventory),
        current_get_unit_price_if_current_get_unit_price_is_not_None=current.get('unit_price') if current.get('unit_price') is not None else '',
    )
    styles = (
        _subcategory_styles(inventory) + _article_page_styles()
        + table_pages.responsive_styles()
    )
    return layout("Artículos", alert(error) + body, styles)


def _event_row(event: dict) -> str:
    return render(
        'web/event_row.html',
        event_at=event['at'],
        event_action=event['action'],
        event_detail=event['detail'],
    )


def events_page(store: Store, page: int = 1) -> str:
    events = store.get_events()
    table = table_pages.table_pages(
        list(reversed(events)), page, ("Fecha", "Acción", "Detalle"),
        _event_row, lambda target: "/registros?" + urlencode({"page": target}),
        "movimientos", "Páginas de registros", "Sin movimientos.", "journey-events",
    )
    try:
        journey_id, _payload = store.get_last_export()
        download = render(
            'web/events_page.html',
            download_form_journey_id_store__export_close_id=download_form(journey_id, store._export_close_id),
        )
    except DomainError:
        download = "<p>Los archivos de la jornada recuperada estarán disponibles cuando vuelva a cerrarse.</p>" if store.journey and any(
            e["action"] == "journey_recovered" and e["journey_id"] == store.journey["id"]
            for e in events
        ) else ""

    body = render(
        'web/events_page_2.html',
        table=table,
        download=download,
    )
    return layout("Registros y exportación", body, table_pages.responsive_styles())


def confirm_page(store: Store, action: str) -> str:
    if action == "recover":
        info = store.recovery_info()
        if not info:
            return layout("Recuperar jornada", "<p>No hay una jornada recuperable.</p>")
        warning = (
            f'Se descartará la jornada actual «{info["active_title"]}» sin contabilizar sus ventas. '
            if info["active_id"] else ""
        )
        warning += "Se reabrirá la jornada anterior al momento previo a su cierre. El catálogo vigente se conserva."
        fields = "".join(f'<input type="hidden" name="{key}" value="{h(info[key])}">'
                         for key in ("close_id", "revision", "active_id"))
        return layout("Recuperar jornada", render(
            'web/confirm_page.html',
            info_title=info['title'],
            warning=warning,
            fields=fields,
        ))
    journey = store.get_journey()
    if not journey or action not in ("close", "discard"):
        message = '<p>Acción no disponible. <a href="/jornada">Volver a jornada</a>.</p>'
        return layout("Confirmar acción", message)

    closing = action == "close"
    if closing:
        title = "Cerrar y contabilizar ventas"
        effect = (
            "Las ventas se agregarán a las estadísticas globales. Después podrás "
            "elegir CSV resumen, CSV detallado, JSON completo o todo en ZIP."
        )
    else:
        title = "Descartar jornada sin contabilizar ventas"
        effect = (
            "Se perderán los datos temporales de esta jornada; sus ventas no se "
            "agregarán a las estadísticas globales."
        )
    button_class = "" if closing else "danger"
    button_label = (
        "Cerrar ventas y elegir descarga CSV / JSON / ZIP"
        if closing else f"Confirmar: {title}"
    )

    body = render(
        'web/confirm_page_2.html',
        journey_title=journey['title'],
        effect=effect,
        action=action,
        journey_id=journey['id'],
        button_class=button_class,
        button_label=button_label,
    )
    return layout(title, body)


def closed_journey_page(journey_id: str, close_id: str | None = None) -> str:
    body = render(
        'web/closed_journey_page.html',
        download_form_journey_id_close_id=download_form(journey_id, close_id),
    )
    return layout("Jornada cerrada", body)


def recovery_button(store: Store) -> str:
    info = store.recovery_info()
    if not info:
        return ""
    return render(
        'web/recovery_button.html',
        info_title=info['title'],
    )


def storage_notices(page):
    """Muestra advertencias de recuperación en todas las páginas de negocio."""
    @wraps(page)
    def render(store, *args, **kwargs):
        result = page(store, *args, **kwargs)
        notices = "".join(alert(message) for message in store.storage.warnings)
        return result.replace("<main>", "<main>" + notices, 1)
    return render


dashboard = storage_notices(dashboard)
journey_page = storage_notices(journey_page)
orders_page = storage_notices(orders_page)
articles_page = storage_notices(articles_page)
events_page = storage_notices(events_page)
confirm_page = storage_notices(confirm_page)
