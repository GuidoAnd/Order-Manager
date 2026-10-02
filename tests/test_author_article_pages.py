"""Cinco artículos por página en los resultados de cada autor de Jornada."""

import asyncio
from copy import deepcopy
import re
from urllib.parse import urlencode

import pytest
from playwright.async_api import async_playwright

from order_manager.api import make_app
from test_mobile import VIEWPORTS, assert_layout, serve_asgi
from test_review_fixes import request


def add_sales(store, name, count):
    author = store.add_author(name)
    if count:
        store.save_order(author["id"], [{
            "name": f"Artículo {number:02d}", "category": "Otros",
            "subcategory": "Otros", "quantity": 1, "unit_price": 100,
        } for number in range(1, count + 1)])
    return author


def table(html, author):
    return html.split(f'id="author-articles-{author["id"]}"', 1)[1].split("</nav>", 1)[0]


def names(html):
    return re.findall(r'data-label="Artículo">(Artículo \d+)</td>', html)


@pytest.mark.parametrize("count", [0, 5, 6, 11])
def test_first_page_has_at_most_five_articles(tmp_path, count):
    app = make_app(tmp_path / "globals.json")
    store = app.state.store
    store.create_journey("Turno")
    author = add_sales(store, "Ana", count)
    _, _, html = request(app, "GET", "/jornada")
    result = table(html, author)
    assert len(names(result)) == min(count, 5)
    assert ("Siguiente" in result) == (count > 5)
    assert "Anterior" not in result
    assert f"{count} artículos" in result
    if not count:
        assert "Sin artículos facturados." in result


def test_pages_keep_totals_data_and_other_author_page(tmp_path):
    app = make_app(tmp_path / "globals.json")
    store = app.state.store
    store.create_journey("Turno")
    first = add_sales(store, "Ana", 11)
    second = add_sales(store, "Bea", 7)
    before = deepcopy(store.get_journey())
    totals = store.get_summary()
    seen = []
    for page in (1, 2, 3):
        query = {f"articles_{first['id']}": page, f"articles_{second['id']}": 2}
        _, _, html = request(app, "GET", "/jornada?" + urlencode(query))
        result = table(html, first)
        seen.extend(names(result))
        assert len(names(table(html, second))) == 2
        assert "Página 2 de 2" in table(html, second)
        assert f"articles_{second['id']}=2" in result
    assert seen == [f"Artículo {number:02d}" for number in range(1, 12)]
    assert len(set(seen)) == 11
    assert store.get_journey() == before
    assert store.get_summary() == totals
    assert totals["by_author"][first["id"]]["revenue"] == 1100
    assert totals["by_author"][second["id"]]["revenue"] == 700


def test_invalid_and_stale_pages_are_clamped(tmp_path):
    app = make_app(tmp_path / "globals.json")
    store = app.state.store
    store.create_journey("Turno")
    author = add_sales(store, "Ana", 6)
    for value, expected in [("bad", 1), ("-2", 1), ("0", 1), ("999", 2)]:
        _, _, html = request(app, "GET", "/jornada?" + urlencode({
            f"articles_{author['id']}": value, "articles_unknown": 900,
        }))
        result = table(html, author)
        assert f"Página {expected} de 2" in result
        assert "articles_unknown" not in result
    order = store.get_journey()["orders"][0]
    store.delete_order(order["id"])
    _, _, html = request(app, "GET", "/jornada?" + urlencode({
        f"articles_{author['id']}": 2,
    }))
    result = table(html, author)
    assert "0 artículos · Página 1 de 1" in result
    assert "Siguiente" not in result and "Anterior" not in result


async def check_pages(tmp_path, viewport):
    app = make_app(tmp_path / "globals.json")
    store = app.state.store
    store.create_journey("Turno")
    first = add_sales(store, "Ana", 11)
    second = add_sales(store, "Bea", 7)
    before = deepcopy(store.get_journey())
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": viewport[0], "height": viewport[1]},
            java_script_enabled=False,
        )
        await context.route("**/*", lambda route: serve_asgi(app, route))
        page = await context.new_page()
        try:
            await page.goto("http://order-manager.test/jornada")
            size = 2 if viewport[0] < 375 else 3 if viewport[0] <= 650 else 4 if viewport[0] < 1024 else 5
            first_table = page.locator(f"#author-articles-{first['id']}").locator(".journey-page-size:visible")
            second_table = page.locator(f"#author-articles-{second['id']}").locator(".journey-page-size:visible")
            assert await first_table.locator("tbody tr").count() == size
            assert await second_table.locator("tbody tr").count() == size
            assert await first_table.get_by_role("link", name="Anterior").count() == 0
            await assert_layout(page, viewport)
            await first_table.get_by_role("link", name="Siguiente").click()
            assert await first_table.locator("tbody tr").count() == size
            assert await first_table.locator("tbody td:first-child").all_text_contents() == [
                f"Artículo {number:02d}" for number in range(size + 1, size * 2 + 1)
            ]
            await second_table.get_by_role("link", name="Siguiente").click()
            first_pages = (11 + size - 1) // size
            second_pages = (7 + size - 1) // size
            assert await first_table.get_by_role("status").inner_text() == f"11 artículos · Página 2 de {first_pages}"
            assert await second_table.locator("tbody tr").count() == min(size, 7 - size)
            for link in await first_table.get_by_role("link").all():
                assert (await link.bounding_box())["height"] >= 44
            colors = await first_table.locator(".pagination").evaluate(
                "node => [...node.children].map(item => getComputedStyle(item).backgroundColor)"
            )
            assert colors[0] != colors[1]
            while await first_table.get_by_role("link", name="Siguiente").count():
                await first_table.get_by_role("link", name="Siguiente").click()
            assert await first_table.locator("tbody tr").count() == (11 - 1) % size + 1
            assert await first_table.get_by_role("link", name="Siguiente").count() == 0
            assert await second_table.get_by_role("status").inner_text() == f"7 artículos · Página 2 de {second_pages}"
            await first_table.get_by_role("link", name="Anterior").click()
            assert await first_table.locator("tbody tr").count() == size
            await assert_layout(page, viewport)
            assert store.get_journey() == before
            assert store.get_summary()["revenue"] == 1800
        finally:
            await context.close()
            await browser.close()


@pytest.mark.parametrize("viewport", VIEWPORTS)
def test_author_articles_mobile_and_desktop(tmp_path, viewport):
    asyncio.run(check_pages(tmp_path, viewport))
