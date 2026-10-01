"""Navegación desplegable y acciones compactas del catálogo."""

import asyncio

import pytest
from playwright.async_api import async_playwright

from order_manager.api import make_app
from test_mobile import VIEWPORTS, assert_layout, navigate_section, serve_asgi
from test_review_fixes import request


def test_shared_navigation_contains_the_same_sections():
    from order_manager.web import layout

    html = layout("Prueba", "")
    desktop = html.split('class="desktop-navigation"', 1)[1].split("</nav>", 1)[0]
    mobile = html.split('class="mobile-navigation"', 1)[1].split("</nav>", 1)[0]
    for path in ("/", "/jornada", "/ordenes", "/articulos", "/registros"):
        assert f'href="{path}"' in desktop
        assert f'href="{path}"' in mobile
    assert '<summary class="button quiet">Menú</summary>' in mobile


def test_article_actions_are_closed_and_preserve_search(tmp_path):
    app = make_app(tmp_path / "globals.json")
    app.state.store.create_journey("Prueba")
    before = app.state.store.get_inventory()
    status, _, html = request(app, "GET", "/articulos?q=caf%C3%A9&page=2")
    assert status == 200
    assert '<details class="article-actions">' in html
    assert '<details class="article-actions" open' not in html
    assert 'name="q" value="café"' in html
    assert 'name="page" value="2"' in html
    assert app.state.store.get_inventory() == before


async def check_navigation_and_actions(tmp_path, viewport):
    app = make_app(tmp_path / "globals.json")
    store = app.state.store
    store.create_journey("Prueba")
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": viewport[0], "height": viewport[1]},
            java_script_enabled=False,
            has_touch=viewport[0] <= 430,
        )
        await context.route("**/*", lambda route: serve_asgi(app, route))
        page = await context.new_page()
        page.set_default_timeout(5000)
        try:
            await page.goto("http://order-manager.test/")
            for section in ("Jornada", "Órdenes", "Artículos", "Registros", "Dashboard"):
                menu = page.locator(".mobile-navigation")
                if viewport[0] < 1024:
                    assert await menu.is_visible()
                    assert await menu.get_attribute("open") is None
                    assert not await menu.get_by_role("link", name=section, exact=True).is_visible()
                    summary = menu.locator("summary")
                    await summary.focus()
                    await page.keyboard.press("Enter")
                    assert await menu.get_attribute("open") is not None
                    await assert_layout(page, viewport)
                    for link in await menu.get_by_role("link").all():
                        assert (await link.bounding_box())["height"] >= 44
                    await page.keyboard.press("Enter")
                    assert await menu.get_attribute("open") is None
                else:
                    assert not await menu.is_visible()
                await navigate_section(page, section)
                title = "Registros y exportación" if section == "Registros" else section
                assert await page.get_by_role("heading", name=title, exact=True).is_visible()
                await assert_layout(page, viewport)
                assert await page.get_by_role("navigation", name="Secciones", exact=True).count() == (
                    0 if viewport[0] < 1024 else 1
                )

            await navigate_section(page, "Artículos")
            await page.get_by_role("searchbox", name="Buscar por nombre").fill("café")
            await page.get_by_role("button", name="Buscar", exact=True).click()
            rows = page.locator("#available-articles tbody tr:visible")
            row = rows.filter(has=page.get_by_text("Cafe", exact=True))
            actions = row.locator(".article-actions")
            assert not await row.get_by_role("button", name="Editar", exact=True).is_visible()
            assert not await row.get_by_role("button", name="Eliminar", exact=True).is_visible()
            toggle = actions.locator("summary")
            assert (await toggle.bounding_box())["height"] >= 44
            await toggle.focus()
            await page.keyboard.press("Enter")
            edit = row.get_by_role("button", name="Editar", exact=True)
            delete = row.get_by_role("button", name="Eliminar", exact=True)
            assert await edit.is_visible() and await delete.is_visible()
            assert await edit.evaluate("node => getComputedStyle(node).backgroundColor") != (
                await delete.evaluate("node => getComputedStyle(node).backgroundColor")
            )
            for button in (edit, delete):
                assert (await button.bounding_box())["height"] >= 44
            await assert_layout(page, viewport)
            await edit.click()
            assert await page.get_by_role("heading", name="Editar artículo", exact=True).is_visible()
            await page.locator('#article-editor input[name="unit_price"]').fill("3100")
            await page.get_by_role("button", name="Guardar artículo").click()
            assert await page.get_by_role("searchbox", name="Buscar por nombre").input_value() == "café"
            assert await actions.get_attribute("open") is None
            await actions.locator("summary").click()
            await row.get_by_role("button", name="Eliminar", exact=True).click()
            assert await page.get_by_role("searchbox", name="Buscar por nombre").input_value() == "café"
            assert not any(item["name"] == "Cafe" for item in store.get_inventory()["articles"])
            await assert_layout(page, viewport)

            await page.set_viewport_size({"width": 1024, "height": 768})
            assert await page.locator(".desktop-navigation").is_visible()
            assert not await page.locator(".mobile-navigation").is_visible()
            await page.set_viewport_size({"width": 1023, "height": 768})
            assert not await page.locator(".desktop-navigation").is_visible()
            await page.locator(".mobile-navigation summary").click()
            assert await page.get_by_role("navigation", name="Secciones", exact=True).count() == 1
            await assert_layout(page, (1023, 768))
        finally:
            await browser.close()


@pytest.mark.parametrize("viewport", VIEWPORTS, ids=lambda size: f"{size[0]}x{size[1]}")
def test_navigation_and_article_actions(tmp_path, viewport):
    asyncio.run(check_navigation_and_actions(tmp_path, viewport))
