"""Edición de categorías originales y formularios antiguos en los cinco anchos."""

import asyncio

import pytest
from playwright.async_api import async_playwright

from order_manager.api import make_app
from order_manager.store import MAX_INPUT_INTEGER
from test_mobile import VIEWPORTS, assert_layout, serve_asgi


async def check_review_fixes(tmp_path, viewport):
    app = make_app(tmp_path / "globals.json")
    store = app.state.store
    store.create_journey("Primera jornada")
    author = store.add_author("Ana")
    order = store.save_order(author["id"], [{
        "name": "Especial de la API", "category": "Categoría original",
        "subcategory": "Subcategoría original", "unit_price": 100, "quantity": 2,
    }, {
        "name": "Café externo", "category": "cafetería",
        "subcategory": "infusiones", "unit_price": 200, "quantity": 1,
    }])
    inventory_before = store.get_inventory()
    position = len(inventory_before["categories"])

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
            await page.goto(f"http://order-manager.test/ordenes?edit={order['id']}")
            assert await page.locator('select[name="category_0"]').input_value() == "Categoría original"
            assert await page.locator(f'select[name="subcategory_0_{position}"]').input_value() == "Subcategoría original"
            assert await page.locator('select[name="category_1"]').input_value() == "Cafetería"
            assert await page.locator('select[name="subcategory_1_3"]').input_value() == "Infusiones"
            await assert_layout(page, viewport)

            await page.get_by_role("button", name="Agregar artículo", exact=True).click()
            await page.get_by_role("button", name="Quitar artículo", exact=True).last.click()
            quantity = page.locator('input[name="quantity_0"]')
            await quantity.fill(str(MAX_INPUT_INTEGER + 1))
            await page.get_by_role("button", name="Guardar orden", exact=True).click()
            assert "Máximo permitido" in await page.get_by_role("alert").inner_text()
            assert store.get_journey()["orders"] == [order]
            await assert_layout(page, viewport)
            await quantity.fill("3")
            await page.get_by_role("button", name="Guardar orden", exact=True).click()
            updated = store.get_journey()["orders"][0]
            assert updated["id"] == order["id"] and updated["total"] == 500
            assert updated["lines"][0]["category"] == "Categoría original"
            assert store.get_inventory() == inventory_before
            await assert_layout(page, viewport)

            await page.goto("http://order-manager.test/jornada")
            editor = page.locator(".journey-name-editor")
            await editor.locator("summary").click()
            await editor.get_by_label("Nombre de la jornada").fill("Cambio de la jornada anterior")
            store.close_journey()
            next_journey = store.create_journey("Segunda jornada")
            await editor.get_by_role("button", name="Guardar", exact=True).click()
            assert "La jornada cambió." in await page.get_by_role("alert").inner_text()
            assert store.get_journey() == next_journey
            await assert_layout(page, viewport)
        finally:
            await context.close()
            await browser.close()


@pytest.mark.parametrize("viewport", VIEWPORTS)
def test_review_fixes_mobile_and_desktop(tmp_path, viewport):
    asyncio.run(check_review_fixes(tmp_path, viewport))
