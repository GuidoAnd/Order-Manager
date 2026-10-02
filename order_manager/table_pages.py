"""Tablas de consulta con paginación adaptable y etiquetas para móvil."""

from html import escape


def h(value: object) -> str:
    return escape(str(value), quote=True)


def table_pages(
    items: list, page: int, headings: tuple[str, ...], render_row,
    page_url, label: str, navigation: str, empty: str, anchor: str,
) -> str:
    views = []
    total = len(items)
    header = "".join(f"<th>{h(heading)}</th>" for heading in headings)
    for size in (5, 4, 3, 2):
        count = max(1, (total + size - 1) // size)
        current = min(max(1, page), count)
        first = (current - 1) * size
        rows = "\n".join(render_row(item) for item in items[first:first + size])
        if not rows:
            rows = f'<tr><td colspan="{len(headings)}">{h(empty)}</td></tr>'
        links = []
        for target, text, color in (
            (current - 1, "Anterior", ""), (current + 1, "Siguiente", " quiet"),
        ):
            if 1 <= target <= count:
                url = page_url(target) + "#" + anchor
                links.append(f'<a class="button{color}" href="{h(url)}">{text}</a>')
        views.append(f"""<div class="table-page-view table-page-{size}">
            <p role="status">{total} {h(label)} · Página {current} de {count}</p>
            <div class="table-wrap responsive-table">
                <table>
                    <thead><tr>{header}</tr></thead>
                    <tbody>{rows}</tbody>
                </table>
            </div>
            <nav class="pagination" aria-label="{h(navigation)}">{''.join(links)}</nav>
        </div>""")
    return f'<div id="{h(anchor)}">' + "\n".join(views) + "</div>"


def responsive_styles() -> str:
    return """<style>
        .table-page-view {
            display: none;
        }
        .table-page-2 {
            display: block;
        }
        @media (min-width: 375px) {
            .table-page-2 {
                display: none;
            }
            .table-page-3 {
                display: block;
            }
        }
        @media (min-width: 651px) {
            .table-page-3 {
                display: none;
            }
            .table-page-4 {
                display: block;
            }
        }
        @media (min-width: 1024px) {
            .table-page-4 {
                display: none;
            }
            .table-page-5 {
                display: block;
            }
        }
    </style>"""
