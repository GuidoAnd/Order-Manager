"""Flujo móvil de regalos/canceladas con artículos y sin facturar."""

import asyncio
from copy import deepcopy
import json
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from order_manager.api import make_app
from test_mobile import VIEWPORTS, assert_layout, serve_asgi


async def check_not_billed(tmp_path, viewport):
    app = make_app(tmp_path / "globals.json")
    store = app.state.store
    store.create_journey("Turno")
    author = store.add_author("Ana")
    catalog = store.get_available_articles()
    coffee = next(item for item in catalog if item["name"] == "Cafe")
    pending = next(item for item in catalog if item["unit_price"] is None)
    store.save_order(author["id"], [{"catalog_id": coffee["id"], "quantity": 1}])
    expected = deepcopy(store.get_summary())
    inventory = store.get_inventory()
    category_position = next(i for i, item in enumerate(inventory["categories"])
                             if item["name"] == "Otros")
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
            editor = page.locator("#order-editor")
            not_billed = page.locator('input[name="order_status"][value="not_billed"]')
            await editor.locator('select[name="author_id"]').select_option(author["id"])
            await page.get_by_label("No facturada (regalo/cancelada)", exact=True).check()
            assert await editor.locator(".line-price:visible").count() == 0
            await editor.get_by_role("button", name="Guardar orden").click()
            assert await page.get_by_role("alert").is_visible()
            assert await not_billed.is_checked()
            assert len(store.get_journey()["orders"]) == 1
            await editor.locator('select[name="catalog_id_0"]').select_option(pending["id"])
            await editor.locator('input[name="quantity_0"]').fill("3")
            await editor.get_by_role("button", name="Agregar artículo").click()
            assert await not_billed.is_checked()
            second = page.locator(".order-line").nth(1)
            await second.get_by_label("Nuevo producto", exact=True).check()
            await second.get_by_label("Nombre", exact=True).fill("Regalo nuevo")
            await second.locator('select[name="category_1"]').select_option(label="Otros")
            await second.locator(f'select[name="subcategory_1_{category_position}"]').select_option(label="Otros")
            await second.get_by_label("Cantidad", exact=True).fill("2")
            await assert_layout(page, viewport)
            await editor.get_by_role("button", name="Guardar orden").click()
            order = store.get_journey()["orders"][-1]
            assert order["status"] == "not_billed" and order["total"] is None
            assert len(order["lines"]) == 2
            assert store.get_summary() == expected
            row = page.locator("#order-results .order-page-size:visible tbody tr").filter(
                has=page.get_by_text("No facturada (regalo/cancelada)", exact=True),
            )
            assert await row.get_by_text("Sin importe", exact=True).is_visible()
            assert await row.get_by_text("Regalo nuevo", exact=False).is_visible()
            await row.locator(".order-actions-menu summary").click()
            await row.get_by_role("button", name="Editar", exact=True).click()
            assert await not_billed.is_checked()
            assert await editor.locator(".line-price:visible").count() == 0
            await page.get_by_label("Venta", exact=True).check()
            assert await editor.locator(".line-price:visible").count() == 2
            await editor.get_by_role("button", name="Guardar orden").click()
            assert await page.get_by_role("alert").is_visible()
            assert await page.get_by_label("Venta", exact=True).is_checked()
            assert store.get_journey()["orders"][-1]["status"] == "not_billed"
            await page.get_by_label("No facturada (regalo/cancelada)", exact=True).check()
            await editor.get_by_role("button", name="Guardar orden").click()
            assert store.get_journey()["orders"][-1]["id"] == order["id"]
            assert store.get_summary() == expected
            await page.goto("http://order-manager.test/jornada")
            orders = page.locator(f"#author-orders-{author['id']} .journey-page-size:visible")
            assert await orders.get_by_text("No facturada (regalo/cancelada)", exact=True).is_visible()
            assert await orders.get_by_text("Sin importe", exact=True).is_visible()
            await assert_layout(page, viewport)
            await page.goto("http://order-manager.test/registros")
            events = page.locator("#journey-events .table-page-view:visible")
            assert order["id"] in await events.inner_text()
            assert "Regalo nuevo" in await events.inner_text()
            await assert_layout(page, viewport)
            await page.goto("http://order-manager.test/jornada")
            await page.get_by_role("link", name="Cerrar y contabilizar ventas").click()
            await page.get_by_role("button", name="Cerrar ventas y elegir descarga CSV / JSON / ZIP").click()
            await page.get_by_role("heading", name="Jornada cerrada", exact=True).wait_for()
            await page.get_by_role("radio", name="JSON completo").check()
            async with page.expect_download() as download_info:
                await page.get_by_role("button", name="Descargar", exact=True).click()
            download = await download_info.value
            assert await download.failure() is None
            data = json.loads(Path(await download.path()).read_text())
            exported = next(item for item in data["orders"] if item["id"] == order["id"])
            assert exported["status"] == "not_billed" and exported["total"] is None
            assert all(line["unit_price"] is None and line["subtotal"] is None for line in exported["lines"])
            assert data["statistics"] == expected
            assert store.get_globals()["orders"] == 1
            assert store.get_globals()["revenue"] == expected["revenue"]
            await page.get_by_role("link", name="Volver al Dashboard", exact=True).click()
            await page.get_by_role("heading", name="Dashboard", exact=True).wait_for()
        finally:
            await browser.close()


@pytest.mark.parametrize("viewport", VIEWPORTS)
def test_not_billed_mobile_and_desktop(tmp_path, viewport):
    asyncio.run(check_not_billed(tmp_path, viewport))
