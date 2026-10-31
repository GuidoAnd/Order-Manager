"""Numeración manual, pantallas propias, plantillas y recuperación persistente."""

import asyncio
from copy import deepcopy
import json
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from order_manager.api import make_app
from order_manager.order_series import validate_serial
from order_manager.state_validation import validate_state
from order_manager.store import DomainError, Store
from order_manager.templating import ENVIRONMENT
from order_manager import web
from test_mobile import VIEWPORTS, assert_layout, serve_asgi, choose_order_article
from test_review_fixes import request
from test_security import exchange, token


@pytest.fixture
def app(tmp_path):
    app = make_app(data_dir=tmp_path / "data")
    app.state.store.create_journey("Jornada")
    app.state.store.add_author("Ana")
    return app


def order_data(app, *, series="10", serial_number=5):
    store = app.state.store
    return {"author_id": store.get_journey()["authors"][0]["id"],
            "series": series, "serial_number": serial_number,
            "lines": [{"catalog_id": store.get_inventory()["articles"][0]["id"],
                       "quantity": 1, "unit_price": 10}]}


@pytest.mark.parametrize("series,number", [("10", 1), ("10", 80), ("20", 81), ("20", 160)])
def test_manual_range_boundaries(app, series, number):
    status, _, body = request(app, "POST", "/api/orders", order_data(app, series=series, serial_number=number))
    assert status == 201
    order = json.loads(body)
    assert (order["series"], order["serial_number"]) == (series, number)


@pytest.mark.parametrize("series,number", [("10", 0), ("10", 81), ("20", 80), ("20", 161),
                                         ("30", 1), ("10", True), ("10", ""), ("10", "1.5")])
def test_invalid_serial_does_not_publish(app, series, number):
    before = deepcopy(app.state.store._state())
    revision = app.state.store.storage.revision
    with pytest.raises(DomainError):
        app.state.store.save_order(**order_data(app, series=series, serial_number=number))
    assert app.state.store._state() == before
    assert app.state.store.storage.revision == revision


def test_duplicates_between_orders_and_authors_are_allowed(app):
    store = app.state.store
    data = order_data(app)
    first = store.save_order(**data)
    second = store.save_order(**data)
    another = store.add_author("Beto")
    third = store.save_order(**{**data, "author_id": another["id"]})
    assert len({o["id"] for o in (first, second, third)}) == 3
    assert [o["serial_number"] for o in (first, second, third)] == [5, 5, 5]
    assert [o["number"] for o in (first, second, third)] == [1, 2, 3]


def test_edit_preserves_id_and_manual_number_does_not_generate_defaults(app):
    store = app.state.store
    first = store.save_order(**order_data(app))
    changed = store.save_order(**order_data(app, series="20", serial_number=90), order_id=first["id"])
    assert changed["id"] == first["id"] and changed["number"] == first["number"]
    html = request(app, "GET", "/ordenes/nueva")[2]
    assert 'name="serial_number"' in html and 'value="90"' not in html
    assert 'value="91"' not in html
    assert 'value="20" selected' not in html
    assert "Serie 20 · 090" in web.orders_page(store)


def test_manual_series_survives_restart_close_and_exact_rollback(app):
    store = app.state.store
    order = store.save_order(**order_data(app, series="20", serial_number=160))
    restarted = Store(store.global_file)
    assert restarted.get_journey()["orders"] == [order]
    exported = json.loads(restarted.close_journey())
    assert exported["orders"][0]["series"] == "20"
    assert exported["orders"][0]["serial_number"] == 160
    restarted.create_journey("Descartada")
    info = restarted.recovery_info()
    restarted.recover_journey(info["close_id"], info["revision"], info["active_id"])
    assert restarted.get_journey()["orders"] == [order]
    assert "Serie 20" in restarted.get_events()[0]["detail"] or any(
        "Serie 20" in event["detail"] for event in restarted.get_events())


def test_invalid_persistent_series_is_detected_and_legacy_is_accepted(app):
    store = app.state.store
    legacy = store.save_order(order_data(app)["author_id"], order_data(app)["lines"])
    validate_state(store._state())
    assert "series" not in legacy
    state = deepcopy(store._state())
    state["journey"]["data"]["orders"][0].update(series="20", serial_number=1)
    with pytest.raises(ValueError):
        validate_state(state)


def test_api_requires_manual_fields_without_echoing_payload(app):
    data = order_data(app)
    data.pop("series")
    data.pop("serial_number")
    status, _, body, _ = exchange(app, "POST", "/api/orders", body=json.dumps(data).encode(),
                                headers=[(b"content-type", b"application/json")])
    assert status == 422 and b'"input"' not in body
    assert app.state.store.get_journey()["orders"] == []


def test_list_editor_routes_and_cancel_do_not_mutate(app):
    store = app.state.store
    order = store.save_order(**order_data(app))
    before = store._state()
    list_html = request(app, "GET", "/ordenes")[2]
    assert "Agregar nueva orden" in list_html and 'id="order-editor"' not in list_html
    assert list_html.index("Agregar nueva orden") < list_html.index("Buscador de Órdenes")
    new_html = request(app, "GET", "/ordenes/nueva?page=2&q=Ana")[2]
    assert 'id="order-editor"' in new_html and 'id="order-results"' not in new_html
    assert 'search_by=all#order-results">Cancelar' in new_html
    assert 'name="q" value="Ana"' in new_html
    edit_html = request(app, "GET", f"/ordenes/{order['id']}/editar")[2]
    assert 'value="10" selected' in edit_html and 'value="5"' in edit_html
    assert store._state() == before
    assert request(app, "GET", "/ordenes/unknown/editar")[0] == 404
    assert request(app, "GET", f"/ordenes?edit={order['id']}")[0] == 303


def test_inline_serial_error_keeps_values_and_context(app):
    store = app.state.store
    values = {"action": "save", "count": "1", "author_id": order_data(app)["author_id"],
              "source_0": "inventory", "catalog_id_0": order_data(app)["lines"][0]["catalog_id"],
              "quantity_0": "1", "unit_price_0": "10", "series": "20", "serial_number": "005",
              "q": "Ana", "page": "2"}
    status, _, html = request(app, "POST", "/ui/orders/form", values, form=True)
    assert status == 400 and 'id="serial-error"' in html
    assert 'aria-invalid="true"' in html and 'value="005"' in html
    assert 'value="20" selected' in html and 'name="q" value="Ana"' in html
    assert store.get_journey()["orders"] == []


def test_journey_actions_and_article_link_adjustments(app):
    html = request(app, "GET", "/jornada")[2]
    assert html.index("Finalizar jornada") < html.index("<h2>Autores</h2>")
    assert "Ver órdenes que lo usan" not in request(app, "GET", "/articulos")[2]


def test_templates_are_reused_without_caching_business_data(app):
    first = ENVIRONMENT.get_template("web/layout.html")
    assert ENVIRONMENT.get_template("web/layout.html") is first
    before = web.journey_page(app.state.store)
    app.state.store.rename_journey('<img src=x onerror="alert(1)">')
    after = web.journey_page(app.state.store)
    assert before != after and '<img src=x onerror=' not in after
    assert '&lt;img' in after


@pytest.mark.parametrize("viewport", VIEWPORTS)
def test_new_interfaces_manual_edit_cancel_and_layout(tmp_path, viewport):
    async def run():
        app = make_app(data_dir=tmp_path / "data")
        store = app.state.store
        store.create_journey("Jornada")
        author = store.add_author("Ana")
        article = store.get_inventory()["articles"][0]
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(viewport={"width": viewport[0], "height": viewport[1]},
                                                java_script_enabled=False,
                                                is_mobile=viewport[0] <= 430,
                                                has_touch=viewport[0] <= 430)
            await context.route("**/*", lambda route: serve_asgi(app, route))
            page = await context.new_page()
            page.set_default_timeout(5000)
            try:
                await page.goto("http://127.0.0.1/ordenes")
                assert await page.locator("#order-editor").count() == 0
                new_order = page.get_by_role("link", name="Agregar nueva orden")
                button_box = await new_order.bounding_box()
                main_box = await page.locator("main").bounding_box()
                assert button_box["height"] >= 56
                assert button_box["width"] >= min(240, main_box["width"])
                assert abs(button_box["x"] + button_box["width"] / 2 -
                           main_box["x"] - main_box["width"] / 2) <= 1
                await assert_layout(page, viewport)
                if viewport[0] <= 430:
                    await new_order.tap()
                else:
                    await new_order.click()
                assert await page.locator("#order-results").count() == 0
                assert await page.get_by_label("Numeración", exact=True).input_value() == ""
                assert await page.get_by_label("Serie", exact=True).locator("option").count() == 3
                await page.get_by_label("Autor", exact=True).select_option(author["id"])
                await page.get_by_label("Serie", exact=True).select_option("20")
                await page.get_by_label("Numeración", exact=True).fill("005")
                await choose_order_article(page, 0, article["name"])
                await page.locator('input[name="quantity_0"]').fill("2")
                await page.locator('input[name="unit_price_0"]').fill("10")
                await page.get_by_role("button", name="Guardar orden").click()
                assert await page.locator("#serial-error").is_visible()
                await assert_layout(page, viewport)
                await page.get_by_label("Numeración", exact=True).fill("081")
                await page.get_by_role("button", name="Guardar orden").click()
                assert len(store.get_journey()["orders"]) == 1
                order = store.get_journey()["orders"][0]
                await page.locator('.order-actions-menu:visible summary').click()
                await page.get_by_role("button", name="Editar orden", exact=True).click()
                assert await page.get_by_label("Numeración", exact=True).input_value() == "81"
                await page.get_by_label("Serie", exact=True).select_option("10")
                await page.get_by_label("Numeración", exact=True).fill("005")
                await page.get_by_role("button", name="Guardar orden").click()
                assert store.get_journey()["orders"][0]["id"] == order["id"]
                await page.get_by_role("link", name="Agregar nueva orden").click()
                assert await page.get_by_label("Numeración", exact=True).input_value() == ""
                await page.get_by_role("link", name="Cancelar", exact=True).click()
                assert await page.get_by_role("heading", name="Buscador de Órdenes", exact=True).is_visible()
                assert len(store.get_journey()["orders"]) == 1
            finally:
                await browser.close()
    asyncio.run(run())
