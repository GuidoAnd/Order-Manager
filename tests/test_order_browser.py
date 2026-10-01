"""Paginación adaptable y búsqueda de órdenes por número o autor."""

import asyncio
from html import unescape
import re
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from playwright.async_api import async_playwright

from order_manager.api import make_app
from order_manager.web import _order_results
from test_mobile import VIEWPORTS, assert_layout, serve_asgi
from test_review_fixes import request


def populate(app, count):
    store = app.state.store
    store.create_journey("Turno")
    authors = [store.add_author("José"), store.add_author("Bea")]
    cafe = next(item for item in store.get_inventory()["articles"] if item["name"] == "Cafe")
    orders = [
        store.save_order(authors[index % 2]["id"], [{
            "catalog_id": cafe["id"], "quantity": 1,
        }])
        for index in range(count)
    ]
    return authors, orders


def numbers(html):
    return [int(value) for value in re.findall(r'data-label="Número">#(\d+)', html)]


def first_view(html):
    return html.split('<div class="order-page-size', 1)[1].split(
        '<div class="order-page-size', 1,
    )[0]


@pytest.mark.parametrize("size", [2, 3, 4, 5])
def test_pages_reach_all_orders_without_duplicates(tmp_path, size):
    app = make_app(tmp_path / "globals.json")
    authors, orders = populate(app, 11)
    before = app.state.store.get_journey()
    pages = (len(orders) + size - 1) // size
    seen = []
    for number in range(1, pages + 1):
        html = _order_results(orders, authors, number, "", "", size)
        found = numbers(html)
        assert 0 < len(found) <= size
        assert set(found) == set(range((number - 1) * size + 1, min(number * size, 11) + 1))
        assert f"Página {number} de {pages}" in html
        seen.extend(found)
    assert sorted(seen) == list(range(1, 12))
    assert app.state.store.get_journey() == before
    assert numbers(_order_results(orders, authors, 999, "", "", size)) == found


def test_search_exact_number_author_accents_and_empty_results(tmp_path):
    app = make_app(tmp_path / "globals.json")
    authors, _ = populate(app, 190)
    app.state.store.rename_author(authors[1]["id"], "Bea 90")
    for query in ["90", "#90", " 90 "]:
        _, _, html = request(app, "GET", "/ordenes?" + urlencode({"q": query}))
        assert numbers(first_view(html)) == [90]
        assert "1 orden · Página 1 de 1" in html
    _, _, html = request(app, "GET", "/ordenes?q=JOSE")
    assert "95 órdenes" in html
    assert all(number % 2 for number in numbers(first_view(html)))
    _, _, html = request(app, "GET", "/ordenes?q=inexistente")
    assert "0 órdenes" in html
    assert "No hay órdenes que coincidan" in html
    assert not numbers(html)
    _, _, html = request(app, "GET", "/ordenes?q=%22%3E%3Cimg%3E")
    assert "<img>" not in html and "&lt;img&gt;" in html
    assert request(app, "GET", "/ordenes?page=0")[0] == 422


def test_filter_and_search_survive_navigation_actions_and_errors(tmp_path):
    app = make_app(tmp_path / "globals.json")
    authors, orders = populate(app, 11)
    state = {"page": "2", "q": "jose", "article": ""}
    _, _, html = request(app, "GET", "/ordenes?" + urlencode(state))
    for url in re.findall(r'href="([^"]+)">(?:Anterior|Siguiente)', first_view(html)):
        fields = parse_qs(urlsplit(unescape(url)).query)
        assert fields["q"] == ["jose"]
    values = {
        **state, "order_id": orders[0]["id"], "author_id": authors[0]["id"],
        "count": "1", "action": "add", "source_0": "new", "name_0": "Especial",
        "category_0": "Otros", "subcategory_0_5": "Otros",
        "new_unit_price_0": "100", "quantity_0": "1",
    }
    status, _, html = request(app, "POST", "/ui/orders/form", values, form=True)
    assert status == 200
    assert 'name="q" value="jose"' in html and 'name="page" value="2"' in html
    status, _, html = request(
        app, "POST", "/ui/orders/form", {**values, "action": "save", "quantity_0": ""},
        form=True,
    )
    assert status == 400
    assert 'name="q" value="jose"' in html
    status, headers, _ = request(
        app, "POST", "/ui/orders/delete",
        {**state, "order_id": orders[-1]["id"]}, form=True,
    )
    assert status == 303
    assert parse_qs(urlsplit(headers["location"]).query)["q"] == ["jose"]
    status, _, html = request(app, "POST", "/ui/orders/delete", {
        **state, "order_id": "missing",
    }, form=True)
    assert status == 404
    assert 'name="q" value="jose"' in html


def test_article_filter_keeps_full_identity_and_combines_with_search(tmp_path):
    app = make_app(tmp_path / "globals.json")
    authors, _ = populate(app, 2)
    store = app.state.store
    line = {"name": "Especial", "category": "Otros", "subcategory": "Otros",
            "quantity": 1, "unit_price": 100}
    matching = [store.save_order(authors[0]["id"], [line]) for _ in range(7)]
    store.save_order(authors[1]["id"], [{**line, "category": "Postres"}])
    article = next(item for item in store.get_available_articles() if item["name"] == "Especial"
                   and item["category"] == "Otros")
    query = {"article": article["id"], "q": "jose", "page": 2}
    _, _, html = request(app, "GET", "/ordenes?" + urlencode(query))
    assert set(numbers(first_view(html))) == {matching[-2]["number"], matching[-1]["number"]}
    assert "7 órdenes" in html
    assert f'name="article" value="{article["id"]}"' in html
    url = unescape(re.search(r'href="([^"]+)">Anterior', first_view(html)).group(1))
    assert parse_qs(urlsplit(url).query)["article"] == [article["id"]]


async def check_order_browser(tmp_path, viewport):
    app = make_app(tmp_path / "globals.json")
    _, orders = populate(app, 91)
    size = 2 if viewport[0] < 375 else 3 if viewport[0] <= 650 else 4 if viewport[0] < 1024 else 5
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": viewport[0], "height": viewport[1]},
            java_script_enabled=False,
        )
        await context.route("**/*", lambda route: serve_asgi(app, route))
        page = await context.new_page()
        try:
            await page.goto("http://order-manager.test/ordenes")
            views = page.locator("#order-results .order-page-size:visible")
            rows = page.locator("#order-results tbody tr:visible")
            assert await views.count() == 1
            assert await rows.count() == size
            first = await rows.locator('input[name="edit"]').evaluate_all(
                "nodes => nodes.map(node => node.value)"
            )
            await views.get_by_role("link", name="Siguiente").click()
            second = await rows.locator('input[name="edit"]').evaluate_all(
                "nodes => nodes.map(node => node.value)"
            )
            assert not set(first) & set(second)
            assert await rows.count() == size
            await assert_layout(page, viewport)
            await views.get_by_role("link", name="Anterior").click()
            assert await rows.locator('input[name="edit"]').evaluate_all(
                "nodes => nodes.map(node => node.value)"
            ) == first

            search = page.get_by_label("Buscar por número o autor")
            await search.fill("90")
            await page.locator(".order-search").get_by_role("button", name="Buscar").click()
            assert await rows.count() == 1
            assert await rows.get_by_text("#90", exact=True).is_visible()
            assert await views.get_by_role("link", name="Siguiente").count() == 0
            await rows.get_by_role("button", name="Editar").click()
            assert await search.input_value() == "90"
            editor = page.locator("#order-editor")
            await editor.locator('input[name="quantity_0"]').fill("")
            await editor.get_by_role("button", name="Guardar orden").click()
            assert await page.get_by_role("alert").is_visible()
            assert await search.input_value() == "90"
            await editor.locator('input[name="quantity_0"]').fill("2")
            await editor.get_by_role("button", name="Guardar orden").click()
            assert await search.input_value() == "90"
            assert await rows.count() == 1
            assert app.state.store.get_journey()["orders"][89]["id"] == orders[89]["id"]
            await rows.get_by_role("button", name="Eliminar").click()
            assert await search.input_value() == "90"
            assert await rows.count() == 0
            assert await views.get_by_text("No hay órdenes que coincidan").is_visible()
            await page.get_by_role("link", name="Limpiar búsqueda").click()
            assert await rows.count() == size
            await search.fill("JOSE")
            await page.locator(".order-search").get_by_role("button", name="Buscar").click()
            assert await rows.count() == size
            assert await rows.locator('td[data-label="Autor"]').all_text_contents() == ["José"] * size
            await views.get_by_role("link", name="Siguiente").click()
            assert await search.input_value() == "JOSE"
            await assert_layout(page, viewport)
            for control in await page.locator(".order-search button, .order-search a, .pagination:visible a").all():
                assert (await control.bounding_box())["height"] >= 44
        finally:
            await context.close()
            await browser.close()


@pytest.mark.parametrize("viewport", VIEWPORTS)
def test_order_browser_mobile_and_desktop(tmp_path, viewport):
    asyncio.run(check_order_browser(tmp_path, viewport))
