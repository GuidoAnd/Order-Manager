"""Órdenes y subtotales por autor con números reales y páginas independientes."""

import asyncio
from copy import deepcopy
import re
from urllib.parse import urlencode

import pytest
from playwright.async_api import async_playwright

from order_manager.api import make_app
from test_mobile import VIEWPORTS, assert_layout, serve_asgi
from test_review_fixes import request


def add_order(store, author, price=100):
    return store.save_order(author["id"], [{
        "name": "Producto" + "x" * 80, "category": "Otros", "subcategory": "Otros",
        "quantity": 1, "unit_price": price,
    }])


def first_table(html, kind, author):
    section = html.split(f'id="author-{kind}-{author["id"]}"', 1)[1]
    return section.split('class="journey-page-size', 2)[1]


@pytest.mark.parametrize("count", [0, 1, 9, 10, 11, 50, 51])
def test_blocks_include_partial_orders_and_exact_subtotals(tmp_path, count):
    app = make_app(tmp_path / "globals.json")
    store = app.state.store
    store.create_journey("Turno")
    author = store.add_author("aa")
    for index in range(count):
        add_order(store, author, index + 1)
    before = deepcopy(store.get_journey())
    seen = []
    blocks = (count + 9) // 10
    for page in range(1, max(1, (blocks + 4) // 5) + 1):
        _, _, html = request(app, "GET", "/jornada?" + urlencode({
            f"subtotals_{author['id']}": page,
        }))
        table = first_table(html, "subtotals", author)
        seen.extend(int(value) for value in re.findall(r"<li>#(\d+)</li>", table))
        assert len(re.findall('data-label="Bloque"', table)) <= 5
        for row in re.findall(r"<tr>(.*?)</tr>", table, re.S):
            numbers = [int(value) for value in re.findall(r"<li>#(\d+)</li>", row)]
            if numbers:
                assert len(numbers) <= 10
                assert f'data-label="Cantidad de órdenes">{len(numbers)}</td>' in row
                assert f'data-label="Subtotal">{sum(numbers)}</td>' in row
        if not count:
            assert "Todavía no hay subtotales." in table
    assert seen == list(range(1, count + 1))
    assert store.get_journey() == before


def test_interleaved_authors_keep_the_actual_order_numbers(tmp_path):
    app = make_app(tmp_path / "globals.json")
    store = app.state.store
    store.create_journey("Turno")
    first = store.add_author("aa")
    second = store.add_author("b")
    for author in (first, first, second, second, first):
        add_order(store, author)
    _, _, html = request(app, "GET", "/jornada")
    first_block = first_table(html, "subtotals", first)
    second_block = first_table(html, "subtotals", second)
    assert re.findall(r"<li>#(\d+)</li>", first_block) == ["1", "2", "5"]
    assert re.findall(r"<li>#(\d+)</li>", second_block) == ["3", "4"]
    assert 'data-label="Subtotal">300</td>' in first_block
    assert 'data-label="Subtotal">200</td>' in second_block


def test_order_pages_keep_running_totals_and_all_navigation_state(tmp_path):
    app = make_app(tmp_path / "globals.json")
    store = app.state.store
    store.create_journey("Turno")
    author = store.add_author("aa")
    for _ in range(61):
        add_order(store, author)
    before = deepcopy(store.get_journey())
    query = {f"orders_{author['id']}": 2, f"subtotals_{author['id']}": 2,
             f"articles_{author['id']}": 1}
    _, _, html = request(app, "GET", "/jornada?" + urlencode(query))
    orders = first_table(html, "orders", author)
    assert re.findall(r'data-label="Orden">#(\d+)', orders) == ["6", "7", "8", "9", "10"]
    assert re.findall(r'data-label="Acumulado del autor">(\d+)', orders) == [
        "600", "700", "800", "900", "1000",
    ]
    assert f"subtotals_{author['id']}=2" in orders
    subtotals = first_table(html, "subtotals", author)
    assert f"orders_{author['id']}=2" in subtotals
    assert re.findall(r"<li>#(\d+)</li>", subtotals) == [str(n) for n in range(51, 62)]
    assert store.get_summary()["revenue"] == 6100
    for value in ("invalid", "0", "-3", "999"):
        _, _, html = request(app, "GET", "/jornada?" + urlencode({
            f"orders_{author['id']}": value, "subtotals_unknown": 800,
        }))
        result = first_table(html, "orders", author)
        expected = 13 if value == "999" else 1
        assert f"Página {expected} de 13" in result
        assert "subtotals_unknown" not in html
    assert store.get_journey() == before


def test_subtotals_recalculate_after_edit_delete_and_clear(tmp_path):
    app = make_app(tmp_path / "globals.json")
    store = app.state.store
    store.create_journey("Turno")
    author = store.add_author("aa")
    orders = [add_order(store, author) for _ in range(11)]
    changed = dict(orders[0]["lines"][0], quantity=2)
    store.save_order(author["id"], [changed], orders[0]["id"])
    store.delete_order(orders[1]["id"])
    _, _, html = request(app, "GET", "/jornada")
    result = first_table(html, "subtotals", author)
    assert 'data-label="Cantidad de órdenes">10</td>' in result
    assert 'data-label="Subtotal">1100</td>' in result
    assert "<li>#2</li>" not in result
    for order in store.get_journey()["orders"]:
        store.delete_order(order["id"])
    _, _, html = request(app, "GET", "/jornada?" + urlencode({
        f"orders_{author['id']}": 20, f"subtotals_{author['id']}": 20,
    }))
    assert "0 bloques · Página 1 de 1" in first_table(html, "subtotals", author)
    assert "Este autor todavía no tiene órdenes." in first_table(html, "orders", author)


async def check_tables(tmp_path, viewport):
    app = make_app(tmp_path / "globals.json")
    store = app.state.store
    store.create_journey("Turno")
    first = store.add_author("Autor" + "x" * 80)
    second = store.add_author("b")
    for _ in range(61):
        add_order(store, first)
    add_order(store, second)
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
            await page.goto("http://order-manager.test/jornada")
            orders = page.locator(f"#author-orders-{first['id']} .journey-page-size:visible")
            subtotals = page.locator(f"#author-subtotals-{first['id']} .journey-page-size:visible")
            assert await orders.locator("tbody tr").count() == size
            assert await subtotals.locator("tbody tr").count() == size
            first_detail = subtotals.locator("tbody tr").first.locator("details")
            assert not await first_detail.locator("ul").is_visible()
            await first_detail.locator("summary").focus()
            await page.keyboard.press("Enter")
            assert await first_detail.locator("li").all_text_contents() == [f"#{n}" for n in range(1, 11)]
            assert (await first_detail.locator("summary").bounding_box())["height"] >= 44
            await assert_layout(page, viewport)
            if viewport[0] <= 650:
                for wrapper in await page.locator(".author-summary .table-wrap:visible").all():
                    assert await wrapper.evaluate("node => node.scrollWidth <= node.clientWidth + 1")
                    assert await wrapper.locator("td[data-label]").count() > 0
            await orders.get_by_role("link", name="Siguiente").click()
            assert await orders.locator('td[data-label="Orden"]').all_text_contents() == [
                f"#{n}" for n in range(size + 1, size * 2 + 1)
            ]
            await subtotals.get_by_role("link", name="Siguiente").click()
            assert await orders.get_by_role("status").inner_text() == (
                f"61 órdenes · Página 2 de {(61 + size - 1) // size}"
            )
            assert await subtotals.locator('td[data-label="Bloque"]').first.inner_text() == str(size + 1)
            for link in await subtotals.get_by_role("link").all():
                assert (await link.bounding_box())["height"] >= 44
            await assert_layout(page, viewport)
            assert store.get_journey() == before
        finally:
            await browser.close()


@pytest.mark.parametrize("viewport", VIEWPORTS)
def test_journey_tables_mobile_and_desktop(tmp_path, viewport):
    asyncio.run(check_tables(tmp_path, viewport))
