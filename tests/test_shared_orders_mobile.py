"""Páginas compartidas, búsqueda de cinco resultados y acciones desplegables."""

import asyncio

import pytest
from playwright.async_api import async_playwright

from order_manager.api import make_app
from test_journey_subtotals import add_order
from test_mobile import VIEWPORTS, assert_layout, serve_asgi


async def check_shared_page(tmp_path, viewport):
    app = make_app(tmp_path / "globals.json")
    store = app.state.store
    store.create_journey("Turno")
    authors = [store.add_author("90 aa")] + [store.add_author(f"Autor {n}") for n in range(1, 7)]
    store.add_author("Sin órdenes")
    for _ in range(8):
        add_order(store, authors[0])
    for author in authors[1:]:
        add_order(store, author)
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
            await page.goto("http://order-manager.test/ordenes")
            view = page.locator("#order-results .order-page-size:visible")
            rows = view.locator("tbody tr")
            assert await view.count() == 1
            assert await rows.count() == 7
            assert set(await rows.locator('td[data-label="Autor"]').all_text_contents()) == {
                author["name"] for author in authors
            }
            assert await view.get_by_role("heading", name="Sin órdenes", exact=True).count() == 0
            assert await view.get_by_role("button", name="Editar", exact=True).count() == 0
            assert await view.get_by_role("button", name="Eliminar", exact=True).count() == 0
            await assert_layout(page, viewport)
            await view.get_by_role("link", name="Siguiente").click()
            assert await rows.count() == size
            assert await rows.locator('td[data-label="Autor"]').all_text_contents() == ["90 aa"] * size

            search = page.get_by_label("Buscar por número o autor")
            await search.fill("90")
            await page.locator(".order-search").get_by_role("button", name="Buscar", exact=True).click()
            assert await rows.count() == 5
            assert await view.get_by_role("status").inner_text() == "8 órdenes · Página 1 de 2"
            await view.get_by_role("link", name="Siguiente").click()
            assert await rows.count() == 3
            await view.get_by_role("link", name="Anterior").click()
            action = rows.first.locator(".order-actions-menu")
            await action.locator("summary").focus()
            await page.keyboard.press("Enter")
            edit = action.get_by_role("button", name="Editar", exact=True)
            delete = action.get_by_role("button", name="Eliminar", exact=True)
            for control in (action.locator("summary"), edit, delete):
                assert (await control.bounding_box())["height"] >= 44
            assert await edit.evaluate("node => getComputedStyle(node).backgroundColor") != (
                await delete.evaluate("node => getComputedStyle(node).backgroundColor")
            )
            await assert_layout(page, viewport)
            await delete.click()
            assert await search.input_value() == "90"
            assert await rows.count() == 5
            assert await view.get_by_role("status").inner_text() == "7 órdenes · Página 1 de 2"
            await search.fill("#90")
            await page.locator(".order-search").get_by_role("button", name="Buscar", exact=True).click()
            assert await rows.count() == 0
            await assert_layout(page, viewport)
        finally:
            await browser.close()


@pytest.mark.parametrize("viewport", VIEWPORTS)
def test_shared_orders_and_numeric_author_mobile(tmp_path, viewport):
    asyncio.run(check_shared_page(tmp_path, viewport))
