"""Órdenes con artículos obligatorios, no facturadas y ajenas a las ventas."""

from copy import deepcopy
import json

import pytest

from order_manager.api import make_app
from order_manager.store import DomainError
from test_review_fixes import request


@pytest.fixture
def active(tmp_path):
    app = make_app(tmp_path / "globals.json")
    app.state.store.create_journey("Turno")
    author = app.state.store.add_author("Ana")
    return app, author


def raw_line(**changes):
    return {"name": "Regalo", "category": "Otros", "subcategory": "Otros",
            "quantity": 2, **changes}


@pytest.mark.parametrize("source", ["priced_inventory", "pending_inventory", "new"])
def test_not_billed_orders_keep_articles_without_any_amount(active, source):
    app, author = active
    store = app.state.store
    if source == "new":
        line = raw_line(unit_price="unused")
    else:
        article = next(item for item in store.get_available_articles()
                       if (item["unit_price"] is None) == (source == "pending_inventory"))
        line = {"catalog_id": article["id"], "quantity": 3, "unit_price": "unused"}
    before = deepcopy(store.get_inventory())
    order = store.save_order(author["id"], [line], status="not_billed")
    assert order["id"] and order["number"] == 1 and order["status"] == "not_billed"
    assert order["total"] is None
    assert order["lines"][0]["unit_price"] is None
    assert order["lines"][0]["subtotal"] is None
    assert order["lines"][0]["name"] and order["lines"][0]["quantity"] > 0
    assert store.get_inventory() == before
    assert store.get_summary()["orders"] == store.get_summary()["units"] == 0
    assert store.get_events()[-1]["action"] == "order_not_billed"
    assert order["id"] in store.get_events()[-1]["detail"]
    assert order["lines"][0]["name"] in store.get_events()[-1]["detail"]


def test_statistics_catalog_subtotals_and_export_exclude_non_sales(active):
    app, author = active
    store = app.state.store
    sale = store.save_order(author["id"], [raw_line(name="Venta", unit_price=100)])
    expected = deepcopy(store.get_summary())
    other = store.add_author("Solo regalos")
    gift = store.save_order(other["id"], [raw_line()], status="not_billed")
    stats = store.get_summary()
    assert {key: stats[key] for key in ("orders", "units", "revenue")} == {
        key: expected[key] for key in ("orders", "units", "revenue")
    }
    assert stats["by_author"][author["id"]] == expected["by_author"][author["id"]]
    assert stats["by_author"][other["id"]]["orders"] == 0
    assert stats["by_author"][other["id"]]["average"] == 0
    assert not any(item["name"] == "Regalo" for item in store.get_available_articles())
    _, _, html = request(app, "GET", "/jornada")
    gift_orders = html.split(f'id="author-orders-{other["id"]}"', 1)[1].split('</div>', 1)[0]
    assert "No facturada (regalo/cancelada)" in gift_orders and "Sin importe" in gift_orders
    subtotals = html.split(f'id="author-subtotals-{other["id"]}"', 1)[1].split('</div>', 1)[0]
    assert "0 bloques" in subtotals
    exported = json.loads(store.close_journey())
    assert exported["orders"] == [sale, gift]
    assert exported["statistics"] == stats
    assert all(item["name"] != "Regalo" for item in exported["new_articles"])
    assert store.get_globals()["orders"] == 1
    assert store.get_globals()["units"] == 2 and store.get_globals()["revenue"] == 200


@pytest.mark.parametrize("lines,status", [
    ([], "not_billed"), ([raw_line(quantity=0)], "not_billed"),
    ([raw_line(name="")], "not_billed"), ([raw_line()], "unknown"),
    ([raw_line()] * 51, "not_billed"), ([raw_line()], "sale"),
])
def test_invalid_orders_are_rejected_without_mutating_data(active, lines, status):
    app, author = active
    before = deepcopy(app.state.store.get_journey())
    with pytest.raises(DomainError):
        app.state.store.save_order(author["id"], lines, status=status)
    assert app.state.store.get_journey() == before


def test_api_status_transitions_preserve_id_and_recalculate_sales(active):
    app, author = active
    status, _, body = request(app, "POST", "/api/orders", {
        "author_id": author["id"], "status": "not_billed", "lines": [raw_line()],
    })
    assert status == 201
    order = json.loads(body)
    identifier = order["id"]
    status, _, body = request(app, "PUT", f"/api/orders/{identifier}", {
        "author_id": author["id"], "status": "sale", "lines": [raw_line(unit_price=100)],
    })
    assert status == 200 and json.loads(body)["id"] == identifier
    assert app.state.store.get_summary()["revenue"] == 200
    status, _, body = request(app, "PUT", f"/api/orders/{identifier}", {
        "author_id": author["id"], "status": "not_billed", "lines": [raw_line(unit_price=999)],
    })
    assert status == 200 and json.loads(body)["total"] is None
    assert app.state.store.get_summary()["orders"] == 0
    for data in ({"lines": [], "status": "not_billed"},
                 {"lines": [raw_line()], "status": "invalid"}):
        assert request(app, "POST", "/api/orders", {"author_id": author["id"], **data})[0] == 422


def test_forms_keep_status_context_and_ignore_prices(active):
    app, author = active
    article = next(item for item in app.state.store.get_available_articles() if item["unit_price"] is None)
    values = {"count": "1", "author_id": author["id"], "source_0": "inventory",
              "catalog_id_0": article["id"], "quantity_0": "2", "unit_price_0": "unused",
              "order_status": "not_billed", "action": "add", "q": "ana", "page": "2"}
    status, _, html = request(app, "POST", "/ui/orders/form", values, form=True)
    assert status == 200 and 'value="not_billed" checked' in html
    values["action"] = "save"
    values["quantity_0"] = "0"
    status, _, html = request(app, "POST", "/ui/orders/form", values, form=True)
    assert status == 400 and 'value="not_billed" checked' in html
    assert 'name="q" value="ana"' in html
    values["quantity_0"] = "2"
    status, headers, _ = request(app, "POST", "/ui/orders/form", values, form=True)
    assert status == 303 and "q=ana" in headers["location"]
    assert app.state.store.get_journey()["orders"][0]["total"] is None
    values["catalog_id_0"] = ""
    assert request(app, "POST", "/ui/orders/form", values, form=True)[0] == 400
    assert len(app.state.store.get_journey()["orders"]) == 1


def test_billed_to_unbilled_removes_temporary_availability_and_keeps_order(active):
    app, author = active
    store = app.state.store
    order = store.save_order(author["id"], [raw_line(unit_price=100)])
    store.save_order(author["id"], [raw_line()], order["id"], status="not_billed")
    assert not any(item["name"] == "Regalo" for item in store.get_available_articles())
    _, _, html = request(app, "GET", f"/ordenes?edit={order['id']}")
    assert 'value="not_billed" checked' in html
    assert 'value="None"' not in html
    assert store.get_summary()["by_article"] == {}
    store.delete_order(order["id"])
    assert not store.get_journey()["orders"]
