"""Edición desplegable del nombre de la jornada abierta."""

import asyncio
from copy import deepcopy

import pytest
from playwright.async_api import async_playwright

from order_manager.api import make_app
from test_mobile import VIEWPORTS, assert_layout, serve_asgi
from test_review_fixes import request


def test_rename_preserves_journey_data(tmp_path):
    app = make_app(tmp_path / "globals.json")
    store = app.state.store
    store.create_journey("Turno")
    store.add_author("Ana")
    before = deepcopy(store.get_journey())
    status, headers, _ = request(
        app, "POST", "/ui/journey",
        {"action": "rename", "title": "  Feria de jueves  "}, form=True,
    )
    assert status == 303
    assert headers["location"] == "/jornada"
    after = store.get_journey()
    assert after["title"] == "Feria de jueves"
    for key in before.keys() - {"title", "events"}:
        assert after[key] == before[key]
    _, _, page = request(app, "GET", "/jornada")
    assert '<details class="journey-name-editor">' in page
    assert '<details class="journey-name-editor" open>' not in page


def test_rename_error_preserves_input_and_opens_editor(tmp_path):
    app = make_app(tmp_path / "globals.json")
    app.state.store.create_journey("Turno")
    status, _, page = request(
        app, "POST", "/ui/journey",
        {"action": "rename", "title": "   "}, form=True,
    )
    assert status == 400
    assert 'class="journey-name-editor" open' in page
    assert 'name="title" value="   "' in page
    assert "El nombre de la jornada es obligatorio." in page
    assert app.state.store.get_journey()["title"] == "Turno"


def test_closed_journey_cannot_be_renamed(tmp_path):
    app = make_app(tmp_path / "globals.json")
    store = app.state.store
    journey = store.create_journey("Turno")
    exported = store.close_journey(journey["id"])
    status, _, page = request(
        app, "POST", "/ui/journey",
        {"action": "rename", "title": "Otro nombre"}, form=True,
    )
    assert status == 409
    assert "journey-name-editor" not in page
    assert store.get_journey() is None
    assert store.last_export == (journey["id"], exported)


async def check_name_editor(tmp_path, viewport):
    app = make_app(tmp_path / "globals.json")
    store = app.state.store
    store.create_journey("Turno")
    journey_id = store.get_journey()["id"]
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
            editor = page.locator(".journey-name-editor")
            toggle = editor.locator("summary")
            name = editor.get_by_label("Nombre de la jornada")
            assert not await name.is_visible()
            assert await toggle.is_visible()
            await assert_layout(page, viewport)

            await toggle.focus()
            await page.keyboard.press("Enter")
            assert await name.is_visible()
            assert await name.input_value() == "Turno"
            await name.fill("Cambio sin guardar")
            await editor.get_by_role("link", name="Cancelar", exact=True).click()
            assert store.get_journey()["title"] == "Turno"
            assert not await name.is_visible()

            await toggle.click()
            new_title = "Jornada de feria — turno de la tarde con nombre largo"
            await name.fill(new_title)
            await editor.get_by_role("button", name="Guardar", exact=True).click()
            assert store.get_journey()["title"] == new_title
            assert store.get_journey()["id"] == journey_id
            assert await editor.get_by_role("heading", name=new_title).is_visible()
            assert not await name.is_visible()
            await assert_layout(page, viewport)

            await toggle.click()
            await assert_layout(page, viewport)
            for control in await editor.locator("button, a.button, summary .button").all():
                box = await control.bounding_box()
                assert box["height"] >= 44
            colors = await editor.locator(".actions").evaluate(
                "node => [...node.children].map(item => getComputedStyle(item).backgroundColor)"
            )
            assert colors[0] != colors[1]

            await name.fill("   ")
            await editor.get_by_role("button", name="Guardar", exact=True).click()
            assert await name.is_visible()
            assert await name.input_value() == "   "
            assert await page.get_by_text("El nombre de la jornada es obligatorio.").is_visible()
            assert store.get_journey()["title"] == new_title
            await assert_layout(page, viewport)
            await editor.get_by_role("link", name="Cancelar", exact=True).click()
            assert not await name.is_visible()
        finally:
            await context.close()
            await browser.close()


@pytest.mark.parametrize("viewport", VIEWPORTS)
def test_name_editor_mobile_and_desktop(tmp_path, viewport):
    asyncio.run(check_name_editor(tmp_path, viewport))
