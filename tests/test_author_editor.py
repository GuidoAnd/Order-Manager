"""Formularios desplegables para agregar, renombrar y eliminar autores."""

import asyncio

import pytest
from playwright.async_api import async_playwright

from order_manager.api import make_app
from test_mobile import VIEWPORTS, assert_layout, serve_asgi
from test_review_fixes import request


def test_rename_preserves_author_orders_and_totals(tmp_path):
    app = make_app(tmp_path / "globals.json")
    store = app.state.store
    store.create_journey("Turno")
    author = store.add_author("Ana")
    cafe = next(item for item in store.get_inventory()["articles"] if item["name"] == "Cafe")
    status, _, _ = request(app, "POST", "/api/orders", {
        "author_id": author["id"],
        "lines": [{"catalog_id": cafe["id"], "quantity": 3}],
    })
    assert status == 201
    before = store.get_journey()["orders"]
    status, _, _ = request(app, "POST", "/ui/journey", {
        "action": "rename_author", "author_id": author["id"], "name": "Anabel",
    }, form=True)
    assert status == 303
    assert store.get_journey()["authors"] == [{"id": author["id"], "name": "Anabel"}]
    assert store.get_journey()["orders"] == before
    status, _, page = request(app, "POST", "/ui/journey", {
        "action": "delete_author", "author_id": author["id"],
    }, form=True)
    assert status == 409
    assert "El autor tiene órdenes" in page
    assert 'class="author-editor author-disclosure" open' in page
    assert store.get_journey()["orders"] == before


@pytest.mark.parametrize("action,name,status", [
    ("add_author", "Ana", 409),
    ("add_author", "   ", 400),
    ("rename_author", "Bea", 400),
    ("rename_author", "   ", 400),
])
def test_author_error_keeps_editor_and_input(tmp_path, action, name, status):
    app = make_app(tmp_path / "globals.json")
    store = app.state.store
    store.create_journey("Turno")
    author = store.add_author("Ana")
    store.add_author("Bea")
    before = store.get_journey()
    actual, _, page = request(app, "POST", "/ui/journey", {
        "action": action, "name": name, "author_id": author["id"],
    }, form=True)
    assert actual == status
    expected = "author-add" if action == "add_author" else "author-editor"
    assert f'class="{expected} author-disclosure" open' in page
    assert f'name="name" value="{name}"' in page
    assert store.get_journey() == before


async def check_author_editors(tmp_path, viewport):
    app = make_app(tmp_path / "globals.json")
    store = app.state.store
    store.create_journey("Turno")
    author = store.add_author("Ana")
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
            add = page.locator(".author-add")
            edit = page.locator(".author-editor")
            names = page.locator(".author-names")
            assert await names.get_by_text("Ana", exact=True).is_visible()
            assert not await add.get_by_label("Nombre del autor").is_visible()
            assert await edit.locator('button[value="delete_author"]').count() == 1
            assert not await edit.locator('button[value="delete_author"]').is_visible()
            await assert_layout(page, viewport)

            await add.locator("summary").focus()
            await page.keyboard.press("Enter")
            await add.get_by_label("Nombre del autor").fill("Cambio sin guardar")
            await add.get_by_role("link", name="Cancelar").click()
            assert len(store.get_journey()["authors"]) == 1
            await add.locator("summary").click()
            assert await add.get_by_label("Nombre del autor").input_value() == ""
            await add.get_by_label("Nombre del autor").fill("Bea")
            await add.get_by_role("button", name="Guardar autor").click()
            assert await names.get_by_text("Bea", exact=True).is_visible()
            assert not await add.get_by_label("Nombre del autor").is_visible()

            await edit.locator("summary").focus()
            await page.keyboard.press("Enter")
            assert not await names.is_visible()
            row = edit.locator(".author-item").filter(
                has=page.locator(f'input[value="{author["id"]}"]')
            )
            await row.get_by_label("Nombre del autor").fill("Bea")
            await row.get_by_role("button", name="Guardar nombre").click()
            assert await row.get_by_label("Nombre del autor").input_value() == "Bea"
            assert await page.get_by_text("Nombre de autor vacío o duplicado.").is_visible()
            await assert_layout(page, viewport)

            await row.get_by_label("Nombre del autor").fill(
                "Ana — nombre largo para verificar la disposición móvil"
            )
            await row.get_by_role("button", name="Guardar nombre").click()
            assert store.get_journey()["authors"][0]["id"] == author["id"]
            assert not await edit.locator('button[value="delete_author"]').first.is_visible()
            assert await names.is_visible()
            await edit.locator("summary").click()
            await assert_layout(page, viewport)
            for control in await edit.locator("button, a.button").all():
                assert (await control.bounding_box())["height"] >= 44
            colors = await edit.locator(".actions").first.evaluate(
                "node => [...node.children].map(item => getComputedStyle(item).backgroundColor)"
            )
            assert colors[0] != colors[1]
            second = edit.locator(".author-item").nth(1)
            # Eliminar no debe validar ni enviar un cambio de nombre pendiente.
            await second.get_by_label("Nombre del autor").fill("")
            await second.get_by_role("button", name="Eliminar").click()
            assert len(store.get_journey()["authors"]) == 1
            assert store.get_journey()["authors"][0]["id"] == author["id"]
            assert await names.is_visible()
            await edit.locator("summary").click()
            await edit.get_by_role("link", name="Cancelar").click()
            assert not await edit.locator('button[value="delete_author"]').is_visible()
            await assert_layout(page, viewport)
        finally:
            await context.close()
            await browser.close()


@pytest.mark.parametrize("viewport", VIEWPORTS)
def test_author_editors_mobile_and_desktop(tmp_path, viewport):
    asyncio.run(check_author_editors(tmp_path, viewport))
