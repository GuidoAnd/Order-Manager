"""Rechazos HTTP, integridad de negocio y protección real en navegador."""

import asyncio
from copy import deepcopy
import json
import re
from urllib.parse import urlencode, urlsplit

import pytest
from playwright.async_api import async_playwright

from order_manager.api import make_app
from order_manager.security import MAX_BODY
from order_manager.store import DomainError
from test_mobile import VIEWPORTS, assert_layout, serve_asgi


def exchange(app, method="GET", url="/jornada", *, body=b"", headers=None, chunks=None):
    messages = []
    target = urlsplit(url)
    pending = list(chunks if chunks is not None else [body])
    reads = []

    async def receive():
        reads.append(True)
        if not pending:
            return {"type": "http.disconnect"}
        piece = pending.pop(0)
        return {"type": "http.request", "body": piece, "more_body": bool(pending)}

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1", "method": method, "scheme": "http",
        "server": ("127.0.0.1", 80), "client": ("127.0.0.1", 1),
        "path": target.path, "raw_path": target.path.encode(),
        "query_string": target.query.encode(), "root_path": "",
        "headers": headers or [],
    }
    asyncio.run(app(scope, receive, send))
    start = next(item for item in messages if item["type"] == "http.response.start")
    return (start["status"], dict(start["headers"]),
            b"".join(item.get("body", b"") for item in messages), len(reads))


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.delenv("ALLOWED_HOSTS", raising=False)
    return make_app(data_dir=tmp_path / "data")


def token(app):
    response = exchange(app)[2].decode()
    return re.search(r'name="csrf_token" value="([^"]+)"', response).group(1)


def form(app, values, *, extra=None, url="/ui/journey"):
    return exchange(app, "POST", url, body=urlencode(values).encode(), headers=[
        (b"content-type", b"application/x-www-form-urlencoded"), *(extra or []),
    ])


def state(app):
    store = app.state.store
    files = {str(p.relative_to(store.data_dir)): p.read_bytes()
             for p in store.data_dir.rglob("*") if p.is_file() and "logs" not in p.parts}
    return deepcopy(store._state()), store.storage.revision, files


@pytest.mark.parametrize("csrf", [None, "", "invalid", "é"])
def test_invalid_form_token_does_not_mutate(app, csrf):
    before = state(app)
    values = {"action": "create", "title": "Turno"}
    if csrf is not None:
        values["csrf_token"] = csrf
    assert form(app, values)[0] == 403
    assert state(app) == before


@pytest.mark.parametrize("extra", [
    [(b"origin", b"https://example.com")],
    [(b"origin", b"http://127.0.0.1:81")],
    [(b"origin", b"null")],
    [(b"origin", b"http://127.0.0.1.example.com")],
    [(b"referer", b"http://example.com/form")],
    [(b"sec-fetch-site", b"cross-site")],
])
def test_foreign_form_origin_rejected_even_with_valid_token(app, extra):
    before = state(app)
    assert form(app, {"action": "create", "title": "Turno", "csrf_token": token(app)}, extra=extra)[0] == 403
    assert state(app) == before


def test_local_form_and_independent_tabs_work(app):
    csrf = token(app)
    assert token(app) == csrf
    assert form(app, {"action": "create", "title": "Turno", "csrf_token": csrf},
                extra=[(b"origin", b"http://127.0.0.1")])[0] == 303
    assert form(app, {"action": "add_author", "name": "Ana", "csrf_token": csrf},
                extra=[(b"referer", b"http://127.0.0.1/jornada")])[0] == 303
    assert app.state.store.get_journey()["authors"][0]["name"] == "Ana"


def test_restart_invalidates_form_token_without_losing_journey(app):
    csrf = token(app)
    app.state.store.create_journey("Turno")
    restarted = make_app(data_dir=app.state.store.data_dir)
    assert token(restarted) != csrf
    before = state(restarted)
    assert form(restarted, {"action": "add_author", "name": "Ana", "csrf_token": csrf})[0] == 403
    assert state(restarted) == before
    assert restarted.state.store.get_journey()["title"] == "Turno"


@pytest.mark.parametrize("route,method", [("/api/journey", "POST"), ("/api/journey", "PATCH"),
                                        ("/api/orders/id", "DELETE")])
def test_browser_api_cross_site_requests_rejected(app, route, method):
    before = state(app)
    assert exchange(app, method, route, body=b'{"title":"Turno"}', headers=[
        (b"content-type", b"application/json"), (b"origin", b"http://example.com"),
    ])[0] == 403
    assert state(app) == before


@pytest.mark.parametrize("content_type", [b"text/plain", b"application/x-www-form-urlencoded", b"multipart/form-data"])
def test_api_rejects_non_json_mutations(app, content_type):
    before = state(app)
    assert exchange(app, "POST", "/api/journey", body=b'{"title":"Turno"}',
                    headers=[(b"content-type", content_type)])[0] == 415
    assert state(app) == before


def test_local_non_browser_json_client_is_supported(app):
    assert exchange(app, "POST", "/api/journey", body=b'{"title":"Turno"}',
                    headers=[(b"content-type", b"application/json")])[0] == 201


@pytest.mark.parametrize("host", [b"example.com", b"127.0.0.1.example.com", b"localhost@evil.com",
                                b"localhost/path", b"localhost#fragment", b"192.168.1.50:8000"])
def test_untrusted_host_rejected(app, host):
    before = state(app)
    assert exchange(app, headers=[(b"host", host)])[0] == 400
    assert state(app) == before


@pytest.mark.parametrize("host", [b"localhost:8000", b"127.0.0.1:8000", b"[::1]:8000"])
def test_loopback_host_accepted(app, host):
    assert exchange(app, headers=[(b"host", host)])[0] == 200


@pytest.mark.parametrize("host", [b"192.168.1.50:8000", b"ORDER-MANAGER.LOCAL:8000",
                                b"[fd00:0:0:0:0:0:0:1]:8000", b"localhost:8000",
                                b"127.0.0.1:8000", b"[::1]:8000"])
def test_configured_hosts_and_loopback_are_accepted(tmp_path, monkeypatch, host):
    monkeypatch.setenv("ALLOWED_HOSTS", "192.168.1.50, order-manager.local, fd00::1")
    configured = make_app(data_dir=tmp_path / "data")
    assert exchange(configured, headers=[(b"host", host)])[0] == 200
    assert exchange(configured, url="/api/health", headers=[(b"host", host)])[0] == 200


@pytest.mark.parametrize("value", ["*", "*.local", "http://192.168.1.50", "192.168.1.50:8000",
                                 "server/path", "bad host", "bad..host", "-server.local",
                                 "server.local?query", "[fd00::1]"])
def test_invalid_allowed_hosts_fail_before_storage_is_created(tmp_path, monkeypatch, value):
    monkeypatch.setenv("ALLOWED_HOSTS", value)
    with pytest.raises(ValueError, match="ALLOWED_HOSTS"):
        make_app(data_dir=tmp_path / "data")
    assert not (tmp_path / "data").exists()


def test_lan_exception_can_be_removed_on_restart_without_losing_data(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOWED_HOSTS", "192.168.1.50")
    configured = make_app(data_dir=tmp_path / "data")
    host = [(b"host", b"192.168.1.50:8000"), (b"content-type", b"application/json")]
    assert exchange(configured, "POST", "/api/journey", body=b'{"title":"LAN"}', headers=host)[0] == 201
    monkeypatch.setenv("ALLOWED_HOSTS", "")
    assert exchange(configured, headers=host)[0] == 200
    configured.state.store.runtime_log.close()
    restarted = make_app(data_dir=tmp_path / "data")
    assert exchange(restarted, headers=host)[0] == 400
    assert exchange(restarted)[0] == 200
    assert restarted.state.store.get_journey()["title"] == "LAN"


def test_allowed_lan_hosts_still_enforce_origin_token_limits_and_headers(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOWED_HOSTS", "192.168.1.50,order-manager.local")
    configured = make_app(data_dir=tmp_path / "data")
    host = (b"host", b"192.168.1.50:8000")
    csrf = token(configured)
    values = {"action": "create", "title": "LAN", "csrf_token": csrf}
    before = state(configured)
    for extra in [[host, (b"origin", b"http://192.168.1.50:8001")],
                  [host, (b"origin", b"http://order-manager.local:8000")],
                  [host, (b"sec-fetch-site", b"cross-site")]]:
        assert form(configured, values, extra=extra)[0] == 403
    assert form(configured, {**values, "csrf_token": "invalid"}, extra=[host])[0] == 403
    assert exchange(configured, headers=[(b"host", b"192.168.1.51:8000")])[0] == 400
    assert exchange(configured, headers=[(b"host", b"192.168.1.50.evil.com:8000")])[0] == 400
    assert exchange(configured, "POST", "/api/journey", body=b"x" * (MAX_BODY + 1),
                    headers=[host, (b"content-type", b"application/json")])[0] == 413
    assert state(configured) == before
    status, headers, _, _ = form(configured, values, extra=[host, (b"origin", b"http://192.168.1.50:8000")])
    assert status == 303
    assert configured.state.store.get_journey()["title"] == "LAN"
    assert headers[b"cache-control"] == b"no-store"
    assert b"form-action 'self'" in headers[b"content-security-policy"]


@pytest.mark.parametrize("viewport", VIEWPORTS)
def test_two_browser_contexts_can_use_configured_lan_host(tmp_path, monkeypatch, viewport):
    monkeypatch.setenv("ALLOWED_HOSTS", "192.168.1.50")

    async def run():
        configured = make_app(data_dir=tmp_path / "data")
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            contexts = []
            for _ in range(2):
                context = await browser.new_context(
                    viewport={"width": viewport[0], "height": viewport[1]},
                    is_mobile=viewport[0] <= 430, has_touch=viewport[0] <= 430,
                    java_script_enabled=False,
                )
                await context.route("**/*", lambda route: serve_asgi(configured, route))
                contexts.append(context)
            first = await contexts[0].new_page()
            await first.goto("http://192.168.1.50:8000/jornada")
            await first.locator('input[name="title"]').fill("Jornada LAN")
            await first.get_by_role("button", name="Crear jornada").click()
            await first.get_by_role("heading", name="Jornada LAN").wait_for()
            await assert_layout(first, viewport)
            second = await contexts[1].new_page()
            await second.goto("http://192.168.1.50:8000/jornada")
            await second.locator(".author-add summary").click()
            await second.locator('.author-add input[name="name"]').fill("Ana")
            await second.get_by_role("button", name="Guardar autor").click()
            assert await second.locator(".author-names").get_by_text("Ana").is_visible()
            await assert_layout(second, viewport)
            await first.reload()
            assert await first.locator(".author-names").get_by_text("Ana").is_visible()
            assert configured.state.store.get_journey()["authors"][0]["name"] == "Ana"
            await browser.close()

    asyncio.run(run())


def test_stream_size_limit_stops_before_remaining_chunks(app):
    before = state(app)
    status, _, _, reads = exchange(app, "POST", "/api/journey", chunks=[
        b"x" * MAX_BODY, b"x", b"not consumed",
    ], headers=[(b"content-type", b"application/json")])
    assert status == 413 and reads == 2
    assert state(app) == before


def test_announced_oversize_is_rejected_before_reading_body(app):
    status, _, _, reads = exchange(app, "POST", "/api/journey", headers=[
        (b"content-length", str(MAX_BODY + 1).encode()),
    ])
    assert status == 413 and reads == 0


def test_exact_body_limit_is_accepted(app):
    body = b'{"title":"Turno"}'
    body += b" " * (MAX_BODY - len(body))
    assert exchange(app, "POST", "/api/journey", body=body,
                    headers=[(b"content-type", b"application/json")])[0] == 201


@pytest.mark.parametrize("name", [b"host", b"content-type", b"content-length", b"origin"])
def test_ambiguous_security_headers_rejected(app, name):
    assert exchange(app, headers=[(name, b"one"), (name, b"two")])[0] == 400


def test_duplicate_form_fields_and_invalid_encoding_rejected(app):
    csrf = token(app)
    before = state(app)
    prefix = f"csrf_token={csrf}&action=create&title=".encode()
    for body in [prefix + b"A&title=B", prefix + b"%FF", prefix + b"\xff"]:
        assert exchange(app, "POST", "/ui/journey", body=body, headers=[
            (b"content-type", b"application/x-www-form-urlencoded"),
        ])[0] == 400
    assert state(app) == before


@pytest.mark.parametrize("value", ["x" * 201, "A\x00B", "A\nB"])
@pytest.mark.parametrize("interface", ["api", "form", "store"])
def test_shared_text_validation_preserves_state(app, value, interface):
    before = state(app)
    if interface == "api":
        status = exchange(app, "POST", "/api/journey", body=json.dumps({"title": value}).encode(),
                          headers=[(b"content-type", b"application/json")])[0]
        assert status == 400
    elif interface == "form":
        assert form(app, {"action": "create", "title": value, "csrf_token": token(app)})[0] == 400
    else:
        with pytest.raises(DomainError):
            app.state.store.create_journey(value)
    assert state(app) == before


def test_taxonomy_limits_apply_to_orders_and_articles(app):
    store = app.state.store
    store.create_journey("Turno")
    author = store.add_author("Ana")
    before = state(app)
    invalid = {"name": "Producto", "category": "x" * 121, "subcategory": "Sub", "unit_price": 1}
    with pytest.raises(DomainError):
        store.add_article(invalid)
    with pytest.raises(DomainError):
        store.save_order(author["id"], [{**invalid, "quantity": 1}])
    assert state(app) == before


def test_text_boundary_and_unicode_are_supported(app):
    title = "á" * 199 + "😀"
    assert form(app, {"action": "create", "title": title, "csrf_token": token(app)})[0] == 303
    assert app.state.store.get_journey()["title"] == title


@pytest.mark.parametrize("url,status", [("/ordenes?q=" + "x" * 201, 400),
                                       ("/articulos?category=" + "x" * 201, 400),
                                       ("/ordenes?q=" + "x" * 8193, 414)])
def test_search_and_url_limits(app, url, status):
    assert exchange(app, url=url)[0] == status


def test_validation_errors_do_not_echo_payload_or_parser_context(app):
    body = b'{"title":{"private":"PRIVATE_MARKER"}}'
    status, _, response, _ = exchange(app, "POST", "/api/journey", body=body,
                                    headers=[(b"content-type", b"application/json")])
    assert status == 422 and b"PRIVATE_MARKER" not in response
    assert b'"input"' not in response and b'"ctx"' not in response


def test_headers_cover_success_rejections_and_internal_errors(app):
    @app.get("/test-failure")
    def failure():
        raise RuntimeError("PRIVATE_MARKER")

    for method, url, expected in [("GET", "/", 200), ("POST", "/ui/journey", 415),
                                  ("GET", "/test-failure", 500), ("GET", "/api/health", 200)]:
        status, headers, body, _ = exchange(app, method, url)
        assert status == expected
        assert headers[b"x-content-type-options"] == b"nosniff"
        assert headers[b"x-frame-options"] == b"DENY"
        assert headers[b"cache-control"] == b"no-store"
        assert b"script-src 'none'" in headers[b"content-security-policy"]
        assert b"PRIVATE_MARKER" not in body


@pytest.mark.parametrize("viewport", VIEWPORTS)
def test_browser_tokens_csp_and_escaped_text(tmp_path, viewport):
    async def run():
        app = make_app(data_dir=tmp_path / "data")
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(viewport={"width": viewport[0], "height": viewport[1]})
            await context.route("**/*", lambda route: serve_asgi(app, route))
            page = await context.new_page()
            await page.goto("http://127.0.0.1/jornada")
            await page.locator('input[name="title"]').fill('<script>window.attacked=1</script>')
            await page.get_by_role("button", name="Crear jornada").click()
            assert app.state.store.get_journey()["title"] == '<script>window.attacked=1</script>'
            assert await page.evaluate("window.attacked === undefined")
            assert await page.locator('form[method="post"]').count() == await page.locator('input[name="csrf_token"]').count()
            await assert_layout(page, viewport)
            await page.evaluate("""() => {
                const script = document.createElement('script');
                script.textContent = 'window.injected = true';
                document.body.append(script);
            }""")
            assert await page.evaluate("window.injected === undefined")
            await browser.close()
    asyncio.run(run())
