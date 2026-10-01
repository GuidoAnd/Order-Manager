"""Paginación del catálogo vendido y de los movimientos de jornada."""

import asyncio
from copy import deepcopy
import re
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from playwright.async_api import async_playwright

from order_manager.api import make_app
from order_manager.table_pages import table_pages
from order_manager.web import _event_row, _sold_article_row
from test_mobile import VIEWPORTS, assert_layout, serve_asgi
from test_review_fixes import request


def populate(app):
    store = app.state.store
    store.create_journey("Turno")
    author = store.add_author("Ana")
    store.save_order(author["id"], [{
        "name": f"Producto {n:02d}" + "x" * 50, "category": "Otros",
        "subcategory": "Otros", "quantity": n, "unit_price": 100,
    } for n in range(1, 12)])
    for n in range(10):
        store.add_author(f"Autor {n}")
    return store


def first_view(html, anchor):
    return html.split(f'id="{anchor}"', 1)[1].split('class="table-page-view', 2)[1]


@pytest.mark.parametrize("size", [2, 3, 4, 5])
@pytest.mark.parametrize("kind", ["sold", "events"])
def test_every_page_reaches_all_rows_without_duplicates(size, kind):
    if kind == "sold":
        items = [(f"Otros / Otros / Producto {n}", {"units": n, "revenue": n * 100})
                 for n in range(11, 0, -1)]
        renderer = _sold_article_row
        label = "Artículo"
    else:
        items = [{"at": "2026-10-01T00:00:00+00:00", "action": "author_created",
                  "detail": f"Movimiento {n}"} for n in range(11, 0, -1)]
        renderer = _event_row
        label = "Detalle"
    pages = (len(items) + size - 1) // size
    seen = []
    for page in range(1, pages + 1):
        html = table_pages(items, page, ("A", "B", "C"), renderer,
                           lambda target: f"/consulta?page={target}", "filas", "Páginas",
                           "Vacío", "results")
        view = html.split(f'class="table-page-view table-page-{size}"', 1)[1].split("</nav>", 1)[0]
        rows = re.findall(f'data-label="{label}">([^<]+)</td>', view)
        assert len(rows) == min(size, len(items) - (page - 1) * size)
        assert ("Anterior" in view) == (page > 1)
        assert ("Siguiente" in view) == (page < pages)
        seen.extend(rows)
    assert len(seen) == len(set(seen)) == len(items)


def test_sold_navigation_preserves_available_search_and_actions(tmp_path):
    app = make_app(tmp_path / "globals.json")
    store = populate(app)
    before = deepcopy(store.get_journey())
    query = {"q": "café", "category": "Cafetería", "subcategory": "Infusiones",
             "page": 2, "sold_page": 2}
    _, _, html = request(app, "GET", "/articulos?" + urlencode(query))
    sold = first_view(html, "sold-articles")
    assert "11 artículos vendidos · Página 2 de 3" in sold
    assert 'data-label="Artículo">Producto 06' in sold
    assert 'name="sold_page" value="2"' in html
    from html import unescape

    for link in re.findall(r'href="([^"]+)"', sold):
        fields = parse_qs(urlsplit(unescape(link)).query)
        assert fields["page"] == ["2"] and fields["q"] == ["café"]
        assert fields["category"] == ["Cafetería"]
    assert store.get_journey() == before
    cafe = next(item for item in store.get_available_articles() if item["name"] == "Cafe")
    values = {**cafe, "article_id": cafe["id"], "q": "café", "page": 2,
              "sold_page": 2, "unit_price": "bad"}
    status, _, html = request(app, "POST", "/ui/articles", values, form=True)
    assert status == 400 and 'name="sold_page" value="2"' in html
    values["unit_price"] = 3100
    status, headers, _ = request(app, "POST", "/ui/articles", values, form=True)
    assert status == 303
    assert parse_qs(urlsplit(headers["location"]).query)["sold_page"] == ["2"]


def test_empty_stale_and_invalid_pages_do_not_modify_the_journey(tmp_path):
    app = make_app(tmp_path / "globals.json")
    assert "Sin movimientos." in request(app, "GET", "/registros?page=999")[2]
    store = populate(app)
    before = deepcopy(store.get_journey())
    _, _, html = request(app, "GET", "/registros?page=999")
    assert "13 movimientos · Página 3 de 3" in first_view(html, "journey-events")
    _, _, html = request(app, "GET", "/articulos?sold_page=999")
    assert "11 artículos vendidos · Página 3 de 3" in first_view(html, "sold-articles")
    assert store.get_journey() == before
    assert request(app, "GET", "/articulos?sold_page=0")[0] == 422
    assert request(app, "GET", "/registros?page=0")[0] == 422
    store.delete_order(store.get_journey()["orders"][0]["id"])
    _, _, html = request(app, "GET", "/articulos?sold_page=999")
    assert "0 artículos vendidos · Página 1 de 1" in first_view(html, "sold-articles")
    store.discard_journey()
    store.create_journey("Nueva")
    _, _, html = request(app, "GET", "/registros?page=999")
    assert "1 movimientos · Página 1 de 1" in first_view(html, "journey-events")
    assert "Autor 9" not in html


async def check_tables(tmp_path, viewport):
    app = make_app(tmp_path / "globals.json")
    store = populate(app)
    before = deepcopy(store.get_journey())
    size = 2 if viewport[0] < 375 else 3 if viewport[0] <= 650 else 4 if viewport[0] < 1024 else 5
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": viewport[0], "height": viewport[1]},
            java_script_enabled=False,
        )
        await context.route("**/*", lambda route: serve_asgi(app, route))
        page = await context.new_page()
        page.set_default_timeout(5000)
        try:
            await page.goto("http://order-manager.test/articulos?q=caf%C3%A9&page=2")
            sold = page.locator("#sold-articles .table-page-view:visible")
            assert await sold.count() == 1
            assert await sold.locator("tbody tr").count() == size
            seen = []
            while True:
                seen.extend(await sold.locator('td[data-label="Artículo"]').all_text_contents())
                await assert_layout(page, viewport)
                if viewport[0] <= 650:
                    assert await sold.locator(".table-wrap").evaluate(
                        "node => node.scrollWidth <= node.clientWidth + 1"
                    )
                if not await sold.get_by_role("link", name="Siguiente").count():
                    break
                await sold.get_by_role("link", name="Siguiente").click()
                fields = parse_qs(urlsplit(page.url).query)
                assert fields["page"] == ["2"] and fields["q"] == ["café"]
            assert len(seen) == len(set(seen)) == 11
            assert seen[0].startswith("Producto 11") and seen[-1].startswith("Producto 01")
            await sold.get_by_role("link", name="Anterior").click()
            for link in await sold.get_by_role("link").all():
                assert (await link.bounding_box())["height"] >= 44
            await page.goto("http://order-manager.test/registros")
            events = page.locator("#journey-events .table-page-view:visible")
            assert await events.count() == 1
            assert await events.locator("tbody tr").count() == size
            assert await events.locator('td[data-label="Detalle"]').first.inner_text() == "Autor 9"
            seen = []
            while True:
                seen.extend(await events.locator('td[data-label="Detalle"]').all_text_contents())
                await assert_layout(page, viewport)
                if viewport[0] <= 650:
                    assert await events.locator(".table-wrap").evaluate(
                        "node => node.scrollWidth <= node.clientWidth + 1"
                    )
                if not await events.get_by_role("link", name="Siguiente").count():
                    break
                await events.get_by_role("link", name="Siguiente").click()
            assert len(seen) == len(set(seen)) == 13
            assert seen[-1] == "Turno"
            assert store.get_journey() == before
        finally:
            await browser.close()


@pytest.mark.parametrize("viewport", VIEWPORTS)
def test_sold_catalog_and_records_mobile(tmp_path, viewport):
    asyncio.run(check_tables(tmp_path, viewport))
