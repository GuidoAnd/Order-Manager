"""Tablas paginadas de órdenes, subtotales y artículos por autor."""

from html import escape
from urllib.parse import urlencode

from .templating import component, render

from .store import is_sale
from .order_series import serial_label
from .order_batches import subtotal_blocks


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
        author_orders = [order for order in orders if order["author_id"] == author_id]
        totals = {
            "orders": order_count,
            "subtotals": len(subtotal_blocks(author, author_orders)),
            "articles": len(stats["by_author"][author_id]["by_article"]),
        }
        for kind, total in totals.items():
            # Dos es el tamaño mínimo; cada vista acota su propia página.
            maximum = max(1, (total + 1) // 2)
            state[kind][author_id] = min(
                max(1, requested.get(kind, {}).get(author_id, 1)), maximum,
            )
    return state


class NavigationPages(dict):
    def __init__(self, pages: dict, navigation, journey_id: str):
        super().__init__(pages)
        self.navigation = navigation
        self.journey_id = journey_id
        self.token = None


def _page_query(state: dict) -> dict:
    return {
        f"{group}_{key}": value
        for group, pages in state.items() for key, value in pages.items()
        if value > 1
    }


def _navigation(author: dict, kind: str, page: int, count: int, state: dict) -> str:
    links = []
    anchor = f"author-{kind}-{author['id']}"
    for target, label, color in (
        (page - 1, "Anterior", ""), (page + 1, "Siguiente", " quiet"),
    ):
        if 1 <= target <= count:
            query = _page_query(state)
            current = f"{kind}_{author['id']}"
            if target > 1:
                query[current] = target
            else:
                query.pop(current, None)
            encoded = urlencode(query)
            if isinstance(state, NavigationPages) and len(encoded) > 4096:
                if state.token is None:
                    state.token = state.navigation.save(state.journey_id, _page_query(state))
                encoded = urlencode({"pages": state.token, current: target})
            url = "/jornada?" + encoded + "#" + anchor
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
    return render(
        'journey_results/table_view.html',
        size=size,
        total=total,
        labels_kind=labels[kind],
        page=page,
        count=count,
        header=header,
        rows=rows,
        navigation_author_kind_page_count_state=_navigation(author, kind, page, count, state),
    )


def _cells(values: tuple, labels: tuple[str, ...]) -> str:
    return component("cells", values, labels)


def _block(
    author: dict, kind: str, title: str, total: int, state: dict,
    headings: tuple[str, ...], render_row, empty: str,
) -> str:
    views = "\n".join(
        _table_view(author, kind, size, total, state, headings, render_row, empty)
        for size in (5, 4, 3, 2)
    )
    css_class = "author-article-results" if kind == "articles" else f"author-{kind}-results"
    return render(
        'journey_results/block.html',
        css_class=css_class,
        kind=kind,
        author_id=author['id'],
        title=title,
        views=views,
    )


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
        if order.get("series"):
            number += f'<span class="order-series">{h(serial_label(order))}</span>'
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
    blocks = subtotal_blocks(author, orders)
    subtotal_headings = ("Bloque", "Cantidad de órdenes", "Subtotal", "Detalle")

    def subtotal_row(index):
        block = blocks[index]["orders"]
        items = "".join(
            f'<li>#{h(order["number"])}' +
            (f' · {h(serial_label(order))}' if order.get("series") else "") +
            (' · 0 · No facturada' if not is_sale(order) else "") + '</li>'
            for order in block
        )
        detail = render(
            'journey_results/subtotal_row.html',
            items=items,
        )
        return _cells(
            (h(blocks[index]["title"]), h(len(block)),
             h(sum(order["total"] for order in block if is_sale(order))), detail),
            subtotal_headings,
        )

    subtotal_table = _block(
        author, "subtotals", "Subtotales por tanda · hasta 10 órdenes por bloque", len(blocks),
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
    return render(
        'journey_results/responsive_styles.html',
    )
