"""Tablas paginadas de órdenes, subtotales y artículos por autor."""

from html import escape
from urllib.parse import urlencode

from .store import is_sale


def h(value: object) -> str:
    return escape(str(value), quote=True)


def page_values(values: dict, prefix: str) -> dict[str, int]:
    pages = {}
    for key, value in values.items():
        if key.startswith(prefix + "_"):
            try:
                pages[key.removeprefix(prefix + "_")] = max(1, int(value))
            except ValueError:
                pages[key.removeprefix(prefix + "_")] = 1
    return pages


def normalize_pages(
    authors: list[dict], orders: list[dict], stats: dict, requested: dict,
) -> dict[str, dict[str, int]]:
    state = {kind: {} for kind in ("orders", "subtotals", "articles")}
    for author in authors:
        author_id = author["id"]
        order_count = sum(order["author_id"] == author_id for order in orders)
        sale_count = sum(order["author_id"] == author_id and is_sale(order) for order in orders)
        totals = {
            "orders": order_count,
            "subtotals": (sale_count + 9) // 10,
            "articles": len(stats["by_author"][author_id]["by_article"]),
        }
        for kind, total in totals.items():
            # Dos es el tamaño mínimo; cada vista acota su propia página.
            maximum = max(1, (total + 1) // 2)
            state[kind][author_id] = min(
                max(1, requested.get(kind, {}).get(author_id, 1)), maximum,
            )
    return state


def _navigation(author: dict, kind: str, page: int, count: int, state: dict) -> str:
    links = []
    anchor = f"author-{kind}-{author['id']}"
    for target, label, color in (
        (page - 1, "Anterior", ""), (page + 1, "Siguiente", " quiet"),
    ):
        if 1 <= target <= count:
            query = {
                f"{group}_{key}": value
                for group, pages in state.items() for key, value in pages.items()
            }
            query[f"{kind}_{author['id']}"] = target
            url = "/jornada?" + urlencode(query) + "#" + anchor
            links.append(f'<a class="button{color}" href="{h(url)}">{label}</a>')
    labels = {"orders": "Órdenes", "subtotals": "Subtotales", "articles": "Artículos"}
    return (
        f'<nav class="pagination" aria-label="{labels[kind]} de {h(author["name"])}">'
        + "".join(links) + "</nav>"
    )


def _table_view(
    author: dict, kind: str, size: int, total: int, state: dict,
    headings: tuple[str, ...], render_row, empty: str,
) -> str:
    count = max(1, (total + size - 1) // size)
    page = min(state[kind].get(author["id"], 1), count)
    first = (page - 1) * size
    rows = "\n".join(render_row(index) for index in range(first, min(first + size, total)))
    if not rows:
        rows = f'<tr><td colspan="{len(headings)}">{h(empty)}</td></tr>'
    header = "".join(f"<th>{h(label)}</th>" for label in headings)
    labels = {"orders": "órdenes", "subtotals": "bloques", "articles": "artículos"}
    return f"""<div class="journey-page-size journey-page-{size}">
        <p role="status">{total} {labels[kind]} · Página {page} de {count}</p>
        <div class="table-wrap responsive-table">
            <table>
                <thead><tr>{header}</tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
        {_navigation(author, kind, page, count, state)}
    </div>"""


def _cells(values: tuple, labels: tuple[str, ...]) -> str:
    return "<tr>" + "".join(
        f'<td data-label="{h(label)}">{value}</td>'
        for label, value in zip(labels, values)
    ) + "</tr>"


def _block(
    author: dict, kind: str, title: str, total: int, state: dict,
    headings: tuple[str, ...], render_row, empty: str,
) -> str:
    views = "\n".join(
        _table_view(author, kind, size, total, state, headings, render_row, empty)
        for size in (5, 4, 3, 2)
    )
    css_class = "author-article-results" if kind == "articles" else f"author-{kind}-results"
    return f"""<div class="{css_class}" id="author-{kind}-{h(author['id'])}">
        <h4>{h(title)}</h4>
        {views}
    </div>"""


def author_tables(
    author: dict, orders: list[dict], stats: dict, state: dict, article_name,
) -> str:
    headings = ("Orden", "Artículos facturados", "Total de la orden", "Acumulado del autor")
    running = []
    total = 0
    for order in orders:
        if is_sale(order):
            total += order["total"]
        running.append(total)

    def order_row(index):
        order = orders[index]
        lines = "<br>".join(
            f'{h(line["name"])} × {h(line["quantity"])} '
            + (f'({h(line["subtotal"])})' if is_sale(order) else "(sin importe)")
            for line in order["lines"]
        )
        number = f'#{h(order["number"])}'
        if not is_sale(order):
            number += '<span class="order-state">No facturada (regalo/cancelada)</span>'
        amount = h(order["total"]) if is_sale(order) else "Sin importe"
        return _cells(
            (number, lines, amount, h(running[index])),
            headings,
        )

    order_table = _block(
        author, "orders", "Órdenes de este autor", len(orders), state, headings,
        order_row, "Este autor todavía no tiene órdenes.",
    )
    sales = [order for order in orders if is_sale(order)]
    blocks = [sales[index:index + 10] for index in range(0, len(sales), 10)]
    subtotal_headings = ("Bloque", "Cantidad de órdenes", "Subtotal", "Detalle")

    def subtotal_row(index):
        block = blocks[index]
        items = "".join(f'<li>#{h(order["number"])}</li>' for order in block)
        detail = f"""<details class="subtotal-orders">
            <summary class="button quiet">Ver órdenes</summary>
            <ul class="list">{items}</ul>
        </details>"""
        return _cells(
            (h(index + 1), h(len(block)), h(sum(order["total"] for order in block)), detail),
            subtotal_headings,
        )

    subtotal_table = _block(
        author, "subtotals", "Subtotales por bloques de hasta 10 órdenes", len(blocks),
        state, subtotal_headings, subtotal_row, "Todavía no hay subtotales.",
    )
    articles = sorted(
        stats["by_article"].items(), key=lambda item: (-item[1]["units"], item[0].casefold()),
    )
    article_headings = ("Artículo", "Unidades", "Importe")

    def article_row(index):
        name, values = articles[index]
        return _cells(
            (h(article_name(name)), h(values["units"]), h(values["revenue"])),
            article_headings,
        )

    article_table = _block(
        author, "articles", "Artículos facturados por este autor", len(articles),
        state, article_headings, article_row, "Sin artículos facturados.",
    )
    return order_table + subtotal_table + article_table


def responsive_styles() -> str:
    return """<style>
        .author-summary .journey-page-size {
            display: none;
        }
        .author-summary .journey-page-2 {
            display: block;
        }
        @media (min-width: 375px) {
            .author-summary .journey-page-2 {
                display: none;
            }
            .author-summary .journey-page-3 {
                display: block;
            }
        }
        @media (min-width: 651px) {
            .author-summary .journey-page-3 {
                display: none;
            }
            .author-summary .journey-page-4 {
                display: block;
            }
        }
        @media (min-width: 1024px) {
            .author-summary .journey-page-4 {
                display: none;
            }
            .author-summary .journey-page-5 {
                display: block;
            }
        }
    </style>"""
