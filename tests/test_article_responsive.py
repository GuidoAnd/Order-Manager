"""Una sola lista de artículos, incluso con CSS antiguo o no disponible."""

import asyncio
from urllib.parse import urlsplit

import pytest
from playwright.async_api import async_playwright

from order_manager import web
from order_manager.api import make_app
from test_mobile import VIEWPORTS, serve_asgi


def test_stylesheet_url_changes_when_its_content_changes(tmp_path, monkeypatch):
    stylesheet = tmp_path / "styles.css"
    stylesheet.write_text("body { color: black; }")
    monkeypatch.setattr(web, "STYLESHEET", stylesheet)
    first = web.stylesheet_url()
    assert first.startswith("/static/styles.css?v=")
    assert web.stylesheet_url() == first
    stylesheet.write_text("body { color: blue; }")
    second = web.stylesheet_url()
    assert second != first
    assert second in web.layout("Prueba", "")


async def check_article_list(tmp_path, viewport, stylesheet_state):
    app = make_app(tmp_path / "globals.json")
    store = app.state.store
    store.create_journey("Prueba")
    if viewport[0] < 375:
        size = 2
    elif viewport[0] <= 650:
        size = 3
    elif viewport[0] < 1024:
        size = 4
    else:
        size = 5

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": viewport[0], "height": viewport[1]},
            java_script_enabled=False,
        )

        async def route_request(route):
            if urlsplit(route.request.url).path == "/static/styles.css":
                if stylesheet_state == "unavailable":
                    await route.abort()
                else:
                    await route.fulfill(
                        content_type="text/css",
                        body="body { margin: 0; } .article-page-size { display: block; }",
                    )
            else:
                await serve_asgi(app, route)

        await context.route("**/*", route_request)
        page = await context.new_page()
        try:
            await page.goto("http://order-manager.test/articulos")
            if viewport[0] == 320 and stylesheet_state == "previous":
                # Reproduce el fallo: HTML con cuatro vistas y CSS sin las reglas nuevas.
                previous_html = web.articles_page(store).replace(
                    web._article_page_styles(), "",
                )
                await page.set_content(previous_html)
                assert await page.locator(".article-page-size:visible").count() == 4
                await page.goto("http://order-manager.test/articulos")

            views = page.locator(".article-page-size:visible")
            rows = page.locator("#available-articles tbody tr:visible")
            assert await views.count() == 1
            assert await rows.count() == size
            first_ids = await rows.locator('input[name="edit"]').evaluate_all(
                "elements => elements.map(element => element.value)"
            )
            await page.get_by_role("link", name="Siguiente", exact=True).click()
            assert await views.count() == 1
            assert await rows.count() == size
            next_ids = await rows.locator('input[name="edit"]').evaluate_all(
                "elements => elements.map(element => element.value)"
            )
            assert not set(first_ids) & set(next_ids)
            await page.get_by_role("link", name="Anterior", exact=True).click()
            assert await rows.locator('input[name="edit"]').evaluate_all(
                "elements => elements.map(element => element.value)"
            ) == first_ids
            await page.get_by_role("searchbox", name="Buscar por nombre").fill("café")
            await page.get_by_role("button", name="Buscar", exact=True).click()
            assert await views.count() == 1
            assert await rows.count() == min(3, size)
            assert "3 resultados" in await page.get_by_role("status").inner_text()
        finally:
            await browser.close()


@pytest.mark.parametrize("viewport", VIEWPORTS, ids=lambda size: f"{size[0]}x{size[1]}")
@pytest.mark.parametrize("stylesheet_state", ["previous", "unavailable"])
def test_only_one_list_with_old_or_unavailable_stylesheet(
    tmp_path, viewport, stylesheet_state,
):
    asyncio.run(check_article_list(tmp_path, viewport, stylesheet_state))
