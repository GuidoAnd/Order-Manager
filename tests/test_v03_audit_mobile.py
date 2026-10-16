"""Edición del catálogo recuperado y navegación adaptable en Chromium."""

import asyncio

import pytest
from playwright.async_api import async_playwright

from test_mobile import VIEWPORTS, assert_layout, serve_asgi
from test_v03_audit import recovered_app


@pytest.mark.parametrize("viewport", VIEWPORTS)
def test_recovered_catalog_and_journey_pagination(recovered_app, viewport):
    app, updated, added = recovered_app
    store = app.state.store
    original_orders = store.get_journey()["orders"]
    author_id = store.get_journey()["authors"][0]["id"]
    # El caso de URL larga se concentra en el viewport mínimo.
    for index in range(59 if viewport[0] == 320 else 1):
        store.add_author(f"Autor {index:02d}")
    for _ in range(5):
        store.save_order(author_id, [{"catalog_id": updated["id"], "quantity": 1}])

    async def run():
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
                for article in (updated, added):
                    await page.goto("http://127.0.0.1/articulos?edit=" + article["id"])
                    editor = page.locator("#article-editor")
                    assert await editor.get_by_label("Nombre", exact=True).input_value() == article["name"]
                    price = editor.get_by_label("Precio unitario (opcional)")
                    assert await price.input_value() == str(article["unit_price"])
                    await price.fill("-1")
                    await editor.get_by_role("button", name="Guardar artículo").click()
                    assert await page.get_by_role("alert").count() == 1
                    await assert_layout(page, viewport)
                    await price.fill(str(article["unit_price"]))
                    await editor.get_by_role("button", name="Guardar artículo").click()
                    assert await page.get_by_role("alert").count() == 0
                    await assert_layout(page, viewport)

                assert store.get_journey()["orders"][0] == original_orders[0]
                await page.goto("http://127.0.0.1/jornada")
                result = page.locator(f"#author-orders-{author_id} .journey-page-size:visible")
                first_rows = await result.locator("tbody tr").all_text_contents()
                await result.get_by_role("link", name="Siguiente").click()
                assert await page.get_by_role("heading", name="Jornada", exact=True).is_visible()
                assert "Página 2 de" in await result.get_by_role("status").inner_text()
                await assert_layout(page, viewport)
                await result.get_by_role("link", name="Anterior").click()
                assert await result.locator("tbody tr").all_text_contents() == first_rows
                await assert_layout(page, viewport)
            finally:
                await context.close()
                await browser.close()

    asyncio.run(run())


@pytest.mark.parametrize("viewport", VIEWPORTS)
def test_duplicate_line_form_keeps_identity_when_removing_first(recovered_app, viewport):
    app, article, _ = recovered_app
    store = app.state.store
    author_id = store.get_journey()["authors"][0]["id"]
    row = {"catalog_id": article["id"], "quantity": 1}
    order = store.save_order(author_id, [row], series="10", serial_number=1)
    store.update_article(article["id"], {**article, "unit_price": 725})
    order = store.save_order(author_id, [row, row], order["id"])
    kept = order["lines"][1]
    store.delete_article(article["id"])

    async def run():
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": viewport[0], "height": viewport[1]},
                java_script_enabled=False,
            )
            await context.route("**/*", lambda route: serve_asgi(app, route))
            page = await context.new_page()
            try:
                await page.goto("http://127.0.0.1/ordenes/" + order["id"] + "/editar")
                await page.locator('[name="action"][value="remove_0"]').click()
                assert await page.locator('[name="line_id_0"]').input_value() == kept["line_id"]
                await assert_layout(page, viewport)
                await page.get_by_role("button", name="Guardar orden", exact=True).click()
                updated = next(o for o in store.get_journey()["orders"] if o["id"] == order["id"])
                assert updated["lines"] == [kept]
                await assert_layout(page, viewport)
            finally:
                await context.close()
                await browser.close()
    asyncio.run(run())


def test_many_active_pages_use_short_links_in_browser(recovered_app):
    from urllib.parse import urlencode
    app, article, _ = recovered_app
    store = app.state.store
    authors = [store.get_journey()["authors"][0]]
    for index in range(99):
        authors.append(store.add_author(f"Navegación {index:02d}"))
    for author in authors:
        for _ in range(3):
            store.save_order(author["id"], [{"catalog_id": article["id"], "quantity": 1}])
    query = urlencode({"orders_" + author["id"]: 2 for author in authors})
    before = store._state()

    async def run():
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(viewport={"width": 320, "height": 568}, java_script_enabled=False)
            await context.route("**/*", lambda route: serve_asgi(app, route))
            page = await context.new_page()
            try:
                await page.goto("http://127.0.0.1/jornada?" + query)
                first = page.locator(f"#author-orders-{authors[0]['id']} .journey-page-size:visible")
                other = page.locator(f"#author-orders-{authors[1]['id']} .journey-page-size:visible")
                back = first.get_by_role("link", name="Anterior")
                assert "pages=" in await back.get_attribute("href")
                assert len(await back.get_attribute("href")) < 200
                await back.click()
                assert "Página 1 de" in await first.get_by_role("status").inner_text()
                assert "Página 2 de" in await other.get_by_role("status").inner_text()
                await assert_layout(page, (320, 568))
                await first.get_by_role("link", name="Siguiente").click()
                assert "Página 2 de" in await first.get_by_role("status").inner_text()
                assert "Página 2 de" in await other.get_by_role("status").inner_text()
                assert len(page.url) < 250
                await assert_layout(page, (320, 568))
                app.state.journey_navigation._entries.clear()
                await page.reload()
                assert "caducó" in await page.get_by_role("alert").inner_text()
                assert "Página 1 de" in await first.get_by_role("status").inner_text()
                assert "Página 1 de" in await other.get_by_role("status").inner_text()
                assert store._state() == before
            finally:
                await context.close()
                await browser.close()
    asyncio.run(run())
