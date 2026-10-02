"""Rechazo de booleanos numéricos sin modificar ventas ni órdenes no facturadas."""

import json

import pytest

from order_manager.api import make_app
from test_review_fixes import request


@pytest.fixture
def active(tmp_path):
    app = make_app(tmp_path / "globals.json")
    app.state.store.create_journey("Validación numérica")
    author = app.state.store.add_author("Ana")
    return app, author


@pytest.mark.parametrize("method", ["POST", "PUT"])
@pytest.mark.parametrize("order_status", ["sale", "not_billed"])
@pytest.mark.parametrize("field", ["quantity", "unit_price"])
@pytest.mark.parametrize("value", [True, False])
def test_boolean_order_fields_are_rejected_without_changes(
    active, method, order_status, field, value,
):
    app, author = active
    store = app.state.store
    line = {"name": "Especial", "category": "Otros", "subcategory": "Otros",
            "quantity": 2, "unit_price": 100}
    url = "/api/orders"
    if method == "PUT":
        order = store.save_order(author["id"], [line], status=order_status)
        url += f"/{order['id']}"
    before = store.get_journey()
    inventory_before = store.get_inventory()
    globals_before = store.get_globals()

    status, _, body = request(app, method, url, {
        "author_id": author["id"], "status": order_status,
        "lines": [{**line, field: value}],
    })

    assert status == 422
    assert json.loads(body)["detail"][0]["loc"] == ["body", "lines", 0, field]
    assert store.get_journey() == before
    assert store.get_inventory() == inventory_before
    assert store.get_globals() == globals_before


@pytest.mark.parametrize("method", ["POST", "PUT"])
@pytest.mark.parametrize("value", [True, False])
def test_boolean_article_prices_are_rejected_without_changes(active, method, value):
    app, _ = active
    store = app.state.store
    data = {"name": "Especial", "category": "Otros", "subcategory": "Otros",
            "unit_price": 100}
    url = "/api/articles"
    if method == "PUT":
        article = store.add_article(data)
        url += f"/{article['id']}"
    before = store.get_journey()
    inventory_before = store.get_inventory()
    disk_before = store.inventory_file.read_bytes()

    status, _, body = request(app, method, url, {**data, "unit_price": value})

    assert status == 422
    assert json.loads(body)["detail"][0]["loc"] == ["body", "unit_price"]
    assert store.get_journey() == before
    assert store.get_inventory() == inventory_before
    assert store.inventory_file.read_bytes() == disk_before


@pytest.mark.parametrize("quantity,price", [(2, 0), ("2", "0"), (2.0, 0.0)])
def test_valid_numeric_inputs_keep_existing_conversions(active, quantity, price):
    app, author = active
    data = {"name": "Especial", "category": "Otros", "subcategory": "Otros",
            "unit_price": price}
    status, _, body = request(app, "POST", "/api/articles", data)
    assert status == 201
    assert json.loads(body)["unit_price"] == 0

    status, _, body = request(app, "POST", "/api/orders", {
        "author_id": author["id"], "lines": [{**data, "quantity": quantity}],
    })
    assert status == 201
    order = json.loads(body)
    assert order["status"] == "sale"
    assert order["lines"][0]["quantity"] == 2
    assert order["lines"][0]["unit_price"] == 0
    assert order["total"] == 0
    assert app.state.store.get_summary()["units"] == 2


@pytest.mark.parametrize("price_fields", [{}, {"unit_price": None}])
def test_optional_prices_and_not_billed_records_are_preserved(active, price_fields):
    app, author = active
    data = {"name": "Regalo", "category": "Otros", "subcategory": "Otros",
            **price_fields}
    status, _, body = request(app, "POST", "/api/articles", data)
    assert status == 201
    assert json.loads(body)["unit_price"] is None

    status, _, body = request(app, "POST", "/api/orders", {
        "author_id": author["id"], "status": "not_billed",
        "lines": [{**data, "quantity": 2}],
    })
    assert status == 201
    order = json.loads(body)
    assert order["status"] == "not_billed"
    assert order["total"] is None
    assert order["lines"][0]["unit_price"] is None
    assert order["lines"][0]["subtotal"] is None
    store = app.state.store
    assert store.get_summary()["orders"] == store.get_summary()["units"] == 0
    assert store.get_summary()["revenue"] == 0
    assert store.get_events()[-1]["action"] == "order_not_billed"
    assert order["id"] in store.get_events()[-1]["detail"]
