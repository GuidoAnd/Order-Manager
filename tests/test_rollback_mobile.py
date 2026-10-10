"""Confirmación de rollback y descargas posteriores desde 320 px, sin puertos."""
import asyncio

import pytest
from playwright.async_api import async_playwright

from order_manager.api import make_app
from test_mobile import VIEWPORTS, assert_layout, serve_asgi


async def workflow(tmp_path, viewport):
    app = make_app(data_dir=tmp_path)
    store = app.state.store
    target = store.create_journey("Jornada a recuperar")
    author = store.add_author("Ana")
    row = {"name": "Especial", "category": "Otros", "subcategory": "Otros",
           "unit_price": 100, "quantity": 2}
    store.save_order(author["id"], [row])
    store.close_journey()
    current = store.create_journey("Actual que se descartará")
    async with async_playwright() as driver:
        browser = await driver.chromium.launch()
        page = await browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
        await page.route("**/*", lambda route: serve_asgi(app, route))
        try:
            await page.goto("http://test/jornada")
            await page.get_by_role("link", name="Recuperar última jornada").click()
            await page.get_by_role("heading", name="Recuperar jornada", exact=True).wait_for()
            assert await page.get_by_text("Jornada a recuperar", exact=True).is_visible()
            assert "Actual que se descartará" in await page.locator('[role="alert"]').inner_text()
            await assert_layout(page, viewport)
            confirm = page.get_by_role("button", name="Confirmar recuperación")
            cancel = page.get_by_role("link", name="Cancelar", exact=True)
            assert await confirm.evaluate("e => getComputedStyle(e).backgroundColor") != await cancel.evaluate("e => getComputedStyle(e).backgroundColor")
            await cancel.click()
            assert store.get_journey()["id"] == current["id"]
            await page.get_by_role("link", name="Recuperar última jornada").click()
            await page.get_by_role("button", name="Confirmar recuperación").click()
            assert store.get_journey()["id"] == target["id"]
            assert store.get_globals()["journeys"] == 0
            await assert_layout(page, viewport)
            await page.goto("http://test/registros")
            assert await page.get_by_text("Los archivos de la jornada recuperada estarán disponibles cuando vuelva a cerrarse.").is_visible()
            assert await page.get_by_role("button", name="Descargar", exact=True).count() == 0
            await assert_layout(page, viewport)
            await page.goto("http://test/jornada")
            await page.get_by_role("link", name="Cerrar y contabilizar ventas").click()
            await page.get_by_role("button", name="Cerrar ventas y elegir descarga CSV / JSON / ZIP").click()
            assert await page.get_by_role("button", name="Descargar", exact=True).is_visible()
            assert store.get_globals()["journeys"] == 1
            assert store.get_globals()["revenue"] == 200
            await assert_layout(page, viewport)
        finally:
            await browser.close()


@pytest.mark.parametrize("viewport", VIEWPORTS, ids=lambda s: f"{s[0]}x{s[1]}")
def test_rollback_confirmation_and_downloads(tmp_path, viewport):
    asyncio.run(workflow(tmp_path, viewport))
