"""Prueba el flujo principal y la disposición en tamaños móviles y de referencia."""

import asyncio
import json
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import pytest
from playwright.async_api import async_playwright

from order_manager.api import make_app


VIEWPORTS = [(320, 568), (375, 667), (430, 932), (768, 1024), (1366, 768)]


async def serve_asgi(app, route):
    """Responde a Chromium mediante ASGI sin abrir un puerto de red."""
    request = route.request
    request_url = request.url
    method = request.method
    body = request.post_data_buffer or b""
    for _ in range(5):
        url = urlsplit(request_url)
        response_status = 500
        response_headers = []
        response_body = []
        received = False

        async def receive():
            nonlocal received
            if not received:
                received = True
                return {"type": "http.request", "body": body, "more_body": False}
            await asyncio.sleep(0)
            return {"type": "http.disconnect"}

        async def send(message):
            nonlocal response_status, response_headers
            if message["type"] == "http.response.start":
                response_status = message["status"]
                response_headers = message.get("headers", [])
            elif message["type"] == "http.response.body":
                response_body.append(message.get("body", b""))

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": method,
            "scheme": url.scheme,
            "path": url.path,
            "raw_path": url.path.encode(),
            "query_string": url.query.encode(),
            "root_path": "",
            "headers": [(key.lower().encode(), value.encode())
                        for key, value in request.headers.items()],
            "server": (url.hostname, url.port or 80),
            "client": ("127.0.0.1", 0),
            "state": {},
        }
        await app(scope, receive, send)
        headers = {key.decode(): value.decode() for key, value in response_headers}
        if response_status not in (301, 302, 303, 307, 308):
            break
        request_url = urljoin(request_url, headers["location"])
        method = "GET"
        body = b""
    else:
        raise AssertionError("Demasiadas redirecciones")
    await route.fulfill(
        status=response_status,
        headers=headers,
        body=b"".join(response_body),
    )


async def assert_layout(page, viewport):
    """La página cabe; solo las tablas pueden desplazarse horizontalmente."""
    assert await page.locator("link[rel=stylesheet]").evaluate(
        "link => link.sheet && link.sheet.cssRules.length > 0"
    )
    problems = await page.evaluate("""() => {
        const width = window.innerWidth;
        const elements = [...document.querySelectorAll(
            'header, main, footer, .panel, fieldset, .table-wrap, ' +
            'input:not([type=hidden]), select, button, a.button'
        )];
        return {
            documentWidth: document.documentElement.scrollWidth,
            bodyWidth: document.body.scrollWidth,
            outside: elements.filter(element => {
                const rect = element.getBoundingClientRect();
                return !element.closest('.table-wrap') &&
                    (rect.left < -1 || rect.right > width + 1);
            }).map(element => `${element.tagName}.${element.className}: ${
                Math.round(element.getBoundingClientRect().right)}`)
        };
    }""")
    assert problems["documentWidth"] <= viewport[0] + 1, problems
    assert problems["bodyWidth"] <= viewport[0] + 1, problems
    assert not problems["outside"], problems
    for wrapper in await page.locator(".table-wrap:visible").all():
        assert await wrapper.is_visible()
        assert await wrapper.evaluate(
            "node => node.clientWidth <= window.innerWidth"
        )


async def assert_order_buttons(page, viewport):
    add = await page.get_by_role("button", name="Agregar artículo").bounding_box()
    save = await page.get_by_role("button", name="Guardar orden").bounding_box()
    remove = await page.get_by_role("button", name="Quitar artículo").last.bounding_box()
    assert add["height"] >= 44
    assert remove["height"] >= 44
    assert save["height"] > max(add["height"], remove["height"])
    if viewport[0] <= 650:
        assert save["width"] > max(add["width"], remove["width"])
        assert add["y"] - (remove["y"] + remove["height"]) >= 16
        assert save["y"] - (add["y"] + add["height"]) >= 16


async def assert_article_layout(page, viewport):
    await assert_layout(page, viewport)
    if viewport[0] <= 650:
        for wrapper in await page.locator(".responsive-table:visible").all():
            assert await wrapper.evaluate("node => node.scrollWidth <= node.clientWidth + 1")
            for cell in await wrapper.locator("tbody td").all():
                box = await cell.bounding_box()
                assert box["x"] >= 0
                assert box["x"] + box["width"] <= viewport[0] + 1


async def run_mobile_workflow(tmp_path, viewport):
    app = make_app(tmp_path / "globals.json")
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        mobile = viewport[0] <= 430
        context = await browser.new_context(
            viewport={"width": viewport[0], "height": viewport[1]},
            is_mobile=mobile,
            has_touch=mobile,
            java_script_enabled=False,
        )
        await context.route("**/*", lambda route: serve_asgi(app, route))
        page = await context.new_page()
        page.set_default_timeout(5000)
        try:
            await page.goto("http://order-manager.test/")
            assert await page.get_by_role("heading", name="Dashboard").is_visible()
            await assert_layout(page, viewport)

            await page.get_by_role("link", name="Jornada", exact=True).click()
            await assert_layout(page, viewport)
            await page.locator('input[name="title"]').fill("Turno móvil")
            await page.get_by_role("button", name="Crear jornada").click()
            await page.get_by_role("heading", name="Turno móvil").wait_for()
            assert await page.get_by_role("heading", name="Turno móvil").is_visible()
            await assert_layout(page, viewport)

            await page.locator(".author-add summary").click()
            await page.locator('.author-add input[name="name"]').fill("Ana")
            await page.get_by_role("button", name="Guardar autor").click()
            registered = page.locator(".author-names").get_by_text("Ana")
            assert await registered.is_visible()
            await assert_layout(page, viewport)

            await page.get_by_role("link", name="Órdenes").click()
            await assert_layout(page, viewport)
            await assert_order_buttons(page, viewport)
            await page.locator('select[name="author_id"]').select_option(label="Ana")
            await page.locator('select[name="catalog_id_0"]').select_option(
                label="Cafe · 2800"
            )
            await page.locator('input[name="quantity_0"]').fill("3")
            await page.get_by_role("button", name="Agregar artículo").click()
            assert await page.locator("fieldset").count() == 2
            await assert_layout(page, viewport)
            await page.locator('select[name="catalog_id_1"]').select_option(
                label="Agua Villamanaos 600cc · precio a completar"
            )
            await page.locator('input[name="quantity_1"]').fill("2")
            await page.locator('input[name="unit_price_1"]').fill("2500")
            await page.get_by_role("button", name="Guardar orden").click()
            assert await page.get_by_role("cell", name="13400").is_visible()
            order_lines = page.get_by_role(
                "cell", name="Cafe × 3, Agua Villamanaos 600cc × 2"
            )
            assert await order_lines.is_visible()
            await assert_layout(page, viewport)

            await page.get_by_role("button", name="Editar", exact=True).click()
            order_id_field = page.locator(
                'form[action="/ui/orders/form"] input[name="order_id"]'
            )
            order_id = await order_id_field.input_value()
            await page.locator('input[name="new_unit_price_1"]').fill("")
            await page.get_by_role("button", name="Guardar orden").click()
            assert await page.get_by_role("alert").is_visible()
            assert await page.get_by_role("heading", name="Editar orden").is_visible()
            assert await page.locator("fieldset").count() == 2
            assert await order_id_field.input_value() == order_id
            assert await page.locator('input[name="quantity_0"]').input_value() == "3"
            await assert_layout(page, viewport)
            await page.locator('input[name="new_unit_price_1"]').fill("2500")
            await page.get_by_role("button", name="Guardar orden").click()
            assert await page.get_by_role("button", name="Editar", exact=True).count() == 1
            assert await page.get_by_role("cell", name="13400").is_visible()

            await page.get_by_role("link", name="Dashboard").click()
            assert await page.get_by_text("Turno móvil").is_visible()
            assert await page.get_by_role("heading", name="Ana").is_visible()
            assert await page.get_by_text("13400").count() >= 1
            await assert_layout(page, viewport)

            await page.get_by_role("link", name="Artículos").click()
            assert await page.get_by_role(
                "heading", name="Catálogo vendido de la jornada"
            ).is_visible()
            cafe = page.locator("#sold-articles").get_by_text("Cafe", exact=True)
            assert await cafe.is_visible()
            await assert_article_layout(page, viewport)
            available = page.locator("#available-articles tbody tr:visible")
            page_size = 2 if viewport[0] < 375 else 3 if viewport[0] <= 650 else 4 if viewport[0] < 1024 else 5
            assert await available.count() == page_size
            if viewport[0] <= 650:
                pagination = page.get_by_role("navigation", name="Páginas de artículos")
                assert await pagination.evaluate("node => getComputedStyle(node).justifyContent") == "center"
                row_actions = page.locator("#available-articles .row-actions:visible").first
                assert await row_actions.evaluate("node => getComputedStyle(node).alignItems") == "center"
            if viewport[0] == 320:
                for width, expected in [(374, 2), (375, 3), (650, 3), (651, 4), (1023, 4), (1024, 5)]:
                    await page.set_viewport_size({"width": width, "height": viewport[1]})
                    assert await available.count() == expected
                    assert await page.locator(".article-page-size:visible").count() == 1
                    await assert_article_layout(page, (width, viewport[1]))
                await page.set_viewport_size({"width": viewport[0], "height": viewport[1]})
            await page.get_by_role("navigation", name="Páginas de artículos").get_by_role(
                "link", name="Siguiente"
            ).click()
            pages = (68 + page_size - 1) // page_size
            assert await page.get_by_role("status").inner_text() == f"68 resultados · Página 2 de {pages}"
            assert await available.count() == page_size
            await page.get_by_role("searchbox", name="Buscar por nombre").fill("café")
            await page.get_by_role("button", name="Buscar", exact=True).click()
            assert await available.count() == min(3, page_size)
            await available.filter(has=page.get_by_text("Cafe", exact=True)).get_by_role(
                "button", name="Editar"
            ).click()
            assert await page.get_by_role("heading", name="Editar artículo").is_visible()
            await page.locator('#article-editor input[name="unit_price"]').fill("3100")
            await page.get_by_role("button", name="Guardar artículo").click()
            assert await page.get_by_role("searchbox", name="Buscar por nombre").input_value() == "café"
            assert await page.locator("#available-articles").get_by_role("cell", name="3100").is_visible()
            assert app.state.store.get_journey()["orders"][0]["total"] == 13400
            await assert_article_layout(page, viewport)
            await page.get_by_role("link", name="Limpiar búsqueda").click()
            long_name = "Producto" + "x" * 90
            await page.locator('#article-editor input[name="name"]').fill(long_name)
            await page.locator('select[name="category_article"]').select_option(label="Cafetería")
            await page.locator('select[name="subcategory_article_3"]').select_option(label="Infusiones")
            await page.locator('select[name="category_article"]').select_option(label="Bebidas sin alcohol")
            assert not await page.locator('select[name="subcategory_article_3"]').is_visible()
            await page.locator('select[name="subcategory_article_1"]').select_option(label="Aguas minerales")
            await page.locator('select[name="category_article"]').select_option(label="Cafetería")
            assert await page.locator('select[name="subcategory_article_3"]').input_value() == "Infusiones"
            await page.locator('#article-editor input[name="unit_price"]').fill("100")
            await page.get_by_role("button", name="Guardar artículo").click()
            await page.get_by_role("searchbox", name="Buscar por nombre").fill(long_name)
            await page.get_by_role("button", name="Buscar", exact=True).click()
            assert await available.count() == 1
            await assert_article_layout(page, viewport)

            if viewport[0] <= 650:
                for selector in ("#article-editor .actions", "#article-results .actions"):
                    group = page.locator(selector)
                    assert await group.evaluate("node => getComputedStyle(node).justifyContent") == "center"
                save_button = await page.get_by_role("button", name="Guardar artículo").bounding_box()
                editor = await page.locator("#article-editor .actions").bounding_box()
                assert abs(save_button["x"] + save_button["width"] / 2 - editor["x"] - editor["width"] / 2) <= 1

            await page.get_by_role("link", name="Registros").click()
            await assert_layout(page, viewport)

            await page.get_by_role("link", name="Órdenes").click()
            await page.locator('select[name="author_id"]').select_option(label="Ana")
            await page.locator('select[name="catalog_id_0"]').select_option(
                label="Agua Villamanaos 600cc · precio a completar"
            )
            await page.locator('input[name="unit_price_0"]').fill("2500")
            await page.locator('input[name="quantity_0"]').fill("3")
            await page.get_by_role("radio", name="Nuevo producto").check()
            assert not await page.locator('select[name="catalog_id_0"]').is_visible()
            assert await page.locator('input[name="new_unit_price_0"]').input_value() == ""
            await page.locator('input[name="name_0"]').fill("Agua de los cielos")
            await page.locator('input[name="new_unit_price_0"]').fill("900")
            await page.locator('select[name="category_0"]').select_option(
                label="Bebidas sin alcohol"
            )
            subcategory = page.locator('select[name="subcategory_0_1"]')
            await subcategory.select_option(label="Aguas minerales")
            await page.locator('select[name="category_0"]').select_option(label="Cafetería")
            assert not await subcategory.is_visible()
            await page.locator('select[name="subcategory_0_3"]').select_option(label="Infusiones")
            await page.locator('select[name="category_0"]').select_option(
                label="Bebidas sin alcohol"
            )
            assert await subcategory.input_value() == "Aguas minerales"
            await assert_layout(page, viewport)
            await page.get_by_role("button", name="Agregar artículo").click()
            first_line = page.locator("fieldset").first
            assert await first_line.get_by_role("radio", name="Nuevo producto").is_checked()
            assert await page.locator('input[name="name_0"]').input_value() == "Agua de los cielos"
            assert await page.locator('input[name="new_unit_price_0"]').input_value() == "900"
            await page.locator("fieldset").last.get_by_role("button", name="Quitar artículo").click()
            await assert_order_buttons(page, viewport)
            await page.get_by_role("radio", name="Del inventario", exact=True).check()
            assert await page.locator('input[name="unit_price_0"]').input_value() == "2500"
            await page.get_by_role("radio", name="Nuevo producto").check()
            await page.get_by_role("button", name="Guardar orden").click()
            assert await page.get_by_role("cell", name="Agua de los cielos × 3").is_visible()
            assert await page.locator(".order-page-size:visible").get_by_text(
                "2700", exact=True,
            ).is_visible()
            assert len(app.state.store.get_journey()["orders"]) == 2
            await assert_layout(page, viewport)

            await page.get_by_role("link", name="Artículos", exact=True).click()
            await page.get_by_role("searchbox", name="Buscar por nombre").fill("agua de los cielos")
            await page.get_by_role("button", name="Buscar", exact=True).click()
            assert await page.locator("#available-articles tbody tr:visible").count() == 1
            assert await page.locator("#available-articles").get_by_role("button", name="Eliminar").count() == 0
            await assert_article_layout(page, viewport)
            await page.get_by_role("link", name="Ver órdenes que lo usan").click()
            assert await page.get_by_role("cell", name="Agua de los cielos × 3").is_visible()
            assert await page.get_by_role("cell", name="Cafe × 3, Agua Villamanaos 600cc × 2").count() == 0
            assert await page.get_by_role("button", name="Editar", exact=True).count() == 1
            await assert_article_layout(page, viewport)

            await page.get_by_role("link", name="Jornada", exact=True).click()
            await page.get_by_role("link", name="Cerrar y contabilizar ventas").click()
            journey_id = await page.locator('input[name="journey_id"]').input_value()
            await assert_layout(page, viewport)
            async with page.expect_download() as download_info:
                await page.get_by_role("button", name="Cerrar ventas y contabilizarlas").click()
            download = await download_info.value
            assert await download.failure() is None
            exported = json.loads(Path(await download.path()).read_text())
            assert exported["id"] == journey_id
            assert exported["statistics"]["revenue"] == 16100
            await page.get_by_role("heading", name="Dashboard", exact=True).wait_for()
            assert app.state.store.get_journey() is None
            assert app.state.store.get_globals()["revenue"] == 16100
            await assert_layout(page, viewport)
        finally:
            await browser.close()


@pytest.mark.parametrize("viewport", VIEWPORTS, ids=lambda size: f"{size[0]}x{size[1]}")
def test_main_workflow_and_layout(tmp_path, viewport):
    asyncio.run(run_mobile_workflow(tmp_path, viewport))
