"""Prueba el flujo principal y la disposición en tamaños móviles y de referencia."""

import asyncio
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
    for wrapper in await page.locator(".table-wrap").all():
        assert await wrapper.is_visible()
        assert await wrapper.evaluate(
            "node => node.clientWidth <= window.innerWidth"
        )


async def run_mobile_workflow(tmp_path, viewport):
    app = make_app(tmp_path / "globals.json")
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        mobile = viewport[0] <= 430
        context = await browser.new_context(
            viewport={"width": viewport[0], "height": viewport[1]},
            is_mobile=mobile,
            has_touch=mobile,
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

            await page.locator('input[name="name"]').fill("Ana")
            await page.get_by_role("button", name="Guardar autor").click()
            registered = page.locator(".authors-registered").get_by_text("Ana")
            assert await registered.is_visible()
            await assert_layout(page, viewport)

            await page.get_by_role("link", name="Órdenes").click()
            await assert_layout(page, viewport)
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

            await page.get_by_role("link", name="Dashboard").click()
            assert await page.get_by_text("Turno móvil").is_visible()
            assert await page.get_by_role("heading", name="Ana").is_visible()
            assert await page.get_by_text("13400").count() >= 1
            await assert_layout(page, viewport)

            await page.get_by_role("link", name="Artículos").click()
            assert await page.get_by_role(
                "heading", name="Catálogo vendido de la jornada"
            ).is_visible()
            cafe = page.get_by_role("cell", name="Cafetería / Infusiones / Cafe")
            assert await cafe.is_visible()
            await assert_layout(page, viewport)

            await page.get_by_role("link", name="Registros").click()
            await assert_layout(page, viewport)
        finally:
            await browser.close()


@pytest.mark.parametrize("viewport", VIEWPORTS, ids=lambda size: f"{size[0]}x{size[1]}")
def test_main_workflow_and_layout(tmp_path, viewport):
    asyncio.run(run_mobile_workflow(tmp_path, viewport))
