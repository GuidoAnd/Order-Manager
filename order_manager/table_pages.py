"""Tablas de consulta con paginación adaptable y etiquetas para móvil."""

from html import escape

from .templating import render


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
        views.append(render(
            'table_pages/table_pages.html',
            size=size,
            total=total,
            label=label,
            current=current,
            count=count,
            header=header,
            rows=rows,
            navigation=navigation,
            join_links=''.join(links),
        ))
    return f'<div id="{h(anchor)}">' + "\n".join(views) + "</div>"


def responsive_styles() -> str:
    return render(
        'table_pages/responsive_styles.html',
    )
