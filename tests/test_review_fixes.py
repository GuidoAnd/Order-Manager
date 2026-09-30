"""Regresiones de confirmaciones, formularios, exportación, guardado y estadísticas."""

import asyncio
from copy import deepcopy
from html import unescape
import json
import re
from urllib.parse import urlencode, urlsplit

import pytest

from order_manager.api import make_app
from order_manager.store import Store, article_statistics_key, fresh_globals
from order_manager.web import article_statistics_label, articles_page


def request(app, method, url, values=None, *, form=False):
    content_type = "application/x-www-form-urlencoded" if form else "application/json"
    body = urlencode(values) if form else json.dumps(values)
    body = body.encode() if values is not None else b""
    target = urlsplit(url)
    messages = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "path": target.path,
        "raw_path": target.path.encode(),
        "query_string": target.query.encode(),
        "headers": [(b"content-type", content_type.encode())],
        "scheme": "http",
        "server": ("test", 80),
        "client": ("test", 1),
        "root_path": "",
    }
    asyncio.run(app(scope, receive, send))
    start = next(message for message in messages if message["type"] == "http.response.start")
    response = b"".join(message.get("body", b"") for message in messages)
    headers = {key.decode(): value.decode() for key, value in start["headers"]}
    return start["status"], headers, response.decode()


@pytest.fixture
def active_app(tmp_path):
    app = make_app(tmp_path / "globals.json")
    app.state.store.create_journey("Jornada A")
    app.state.store.add_author("Ana")
    return app


def confirm(app, action, journey_id, interface):
    values = {"journey_id": journey_id} if journey_id is not None else {}
    if interface == "ui":
        values.update(action=action, confirm="yes")
        return request(app, "POST", "/ui/journey", values, form=True)
    return request(app, "POST", f"/api/journey/{action}", values)


@pytest.mark.parametrize("action", ["close", "discard"])
@pytest.mark.parametrize("interface", ["ui", "api"])
@pytest.mark.parametrize("missing_id", [False, True])
def test_old_or_missing_confirmation_preserves_current_journey(
    active_app, action, interface, missing_id,
):
    store = active_app.state.store
    previous_id = store.get_journey()["id"]
    status, _, page = request(active_app, "GET", f"/confirmar/{action}")
    assert status == 200
    assert f'name="journey_id" value="{previous_id}"' in page
    store.discard_journey()
    current = store.create_journey("Jornada B")
    original_globals = store.get_globals()

    status, _, _ = confirm(
        active_app, action, None if missing_id else previous_id, interface,
    )
    assert status == (422 if missing_id and interface == "api" else 409)
    assert store.get_journey() == current
    assert store.get_globals() == original_globals
    assert not store.global_file.exists()

    status, _, _ = confirm(active_app, action, current["id"], interface)
    assert status == (303 if interface == "ui" and action == "discard"
                      else 204 if action == "discard" else 200)
    assert store.get_journey() is None


@pytest.mark.parametrize("editing", [False, True])
def test_order_validation_retains_form_and_retry_does_not_duplicate(active_app, editing):
    store = active_app.state.store
    author = store.get_journey()["authors"][0]
    coffee = next(a for a in store.get_available_articles() if a["name"] == "Cafe")
    order_id = ""
    if editing:
        order = store.save_order(author["id"], [{"catalog_id": coffee["id"], "quantity": 1}])
        order_id = order["id"]
    before = store.get_journey()
    values = {
        "action": "save", "count": "2", "order_id": order_id, "author_id": author["id"],
        "source_0": "inventory", "catalog_id_0": coffee["id"], "quantity_0": "3",
        "source_1": "new", "name_1": "Especial", "category_1": "Otros",
        "subcategory_1_5": "Otros", "quantity_1": "2", "new_unit_price_1": "",
    }
    status, _, page = request(active_app, "POST", "/ui/orders/form", values, form=True)
    assert status == 400
    assert page.count('<fieldset class="order-line">') == 2
    assert f'name="order_id" value="{order_id}"' in page
    assert f'<option value="{author["id"]}" selected>' in page
    assert f'<option value="{coffee["id"]}" selected>' in page
    assert 'name="name_1" value="Especial"' in page
    assert "<h2>Editar orden</h2>" in page if editing else "<h2>Crear orden</h2>" in page
    assert store.get_journey() == before

    values["new_unit_price_1"] = "100"
    status, _, _ = request(active_app, "POST", "/ui/orders/form", values, form=True)
    assert status == 303
    orders = store.get_journey()["orders"]
    assert len(orders) == 1
    assert orders[0]["total"] == 8600
    if editing:
        assert orders[0]["id"] == order_id


def test_new_product_ignores_previous_inventory_selection_and_price(active_app):
    store = active_app.state.store
    author = store.get_journey()["authors"][0]
    water = next(a for a in store.get_available_articles() if a["unit_price"] is None)
    inventory = store.get_inventory()
    values = {
        "action": "save", "count": "1", "author_id": author["id"],
        "source_0": "new", "catalog_id_0": water["id"], "unit_price_0": "2500",
        "name_0": "Agua de los cielos", "category_0": "Otros",
        "subcategory_0_5": "Otros", "new_unit_price_0": "900", "quantity_0": "3",
    }
    status, _, _ = request(active_app, "POST", "/ui/orders/form", values, form=True)
    assert status == 303
    line = store.get_journey()["orders"][0]["lines"][0]
    assert line["name"] == "Agua de los cielos"
    assert line["unit_price"] == 900
    assert line["subtotal"] == 2700
    assert store.get_inventory() == inventory
    assert any(a["name"] == line["name"] for a in store.get_available_articles())


def test_inventory_mode_ignores_inactive_new_product_fields(active_app):
    store = active_app.state.store
    author = store.get_journey()["authors"][0]
    coffee = next(a for a in store.get_available_articles() if a["name"] == "Cafe")
    values = {
        "action": "save", "count": "1", "author_id": author["id"],
        "source_0": "inventory", "catalog_id_0": coffee["id"], "quantity_0": "2",
        "name_0": "No guardar", "category_0": "Inexistente", "new_unit_price_0": "-1",
    }
    status, _, _ = request(active_app, "POST", "/ui/orders/form", values, form=True)
    assert status == 303
    order = store.get_journey()["orders"][0]
    assert order["lines"][0]["name"] == "Cafe"
    assert order["total"] == 5600


@pytest.mark.parametrize("changes", [
    {"new_unit_price_0": ""},
    {"category_0": "Categoría inexistente"},
    {"subcategory_0_5": "Infusiones"},
    {"source_0": "invalid"},
    {"source_0": "inventory", "catalog_id_0": ""},
])
def test_invalid_order_source_or_category_keeps_journey_intact(active_app, changes):
    store = active_app.state.store
    values = {
        "action": "save", "count": "1",
        "author_id": store.get_journey()["authors"][0]["id"],
        "source_0": "new", "name_0": "Especial", "category_0": "Otros",
        "subcategory_0_5": "Otros", "quantity_0": "1", "new_unit_price_0": "100",
        **changes,
    }
    original = store.get_journey()
    status, _, page = request(active_app, "POST", "/ui/orders/form", values, form=True)
    assert status == 400
    assert 'role="alert"' in page
    assert store.get_journey() == original


def test_closed_page_download_never_returns_another_journey(active_app):
    store = active_app.state.store
    first_id = store.get_journey()["id"]
    status, _, page = confirm(active_app, "close", first_id, "ui")
    assert status == 200
    download_url = unescape(re.search(r'<iframe src="([^"]+)"', page).group(1))
    assert f"journey_id={first_id}" in download_url
    status, headers, body = request(active_app, "GET", download_url)
    assert status == 200
    assert first_id in headers["content-disposition"]
    assert json.loads(body)["id"] == first_id
    _, _, events_page = request(active_app, "GET", "/registros")
    assert download_url in events_page

    second = store.create_journey("Jornada B")
    confirm(active_app, "close", second["id"], "api")
    status, headers, body = request(active_app, "GET", download_url)
    assert status == 404
    assert "ya no está disponible" in json.loads(body)["detail"]
    assert "content-disposition" not in headers
    status, _, body = request(active_app, "GET", "/api/exports/last")
    assert status == 200
    assert json.loads(body)["id"] == second["id"]


@pytest.mark.parametrize("interface", ["ui", "api"])
def test_failed_close_keeps_data_and_can_retry_once(active_app, monkeypatch, interface):
    store = active_app.state.store
    store.close_journey()
    store.create_journey("Jornada B")
    author = store.add_author("Beto")
    store.save_order(author["id"], [{
        "name": "Especial", "category": "Otros", "subcategory": "Casa",
        "unit_price": 100, "quantity": 3,
    }])
    journey = store.get_journey()
    globals_before = store.get_globals()
    export_before = store.get_last_export()
    disk_before = store.global_file.read_bytes()

    def fail_replace(*_args):
        raise OSError("detalle técnico que no debe publicarse")

    with monkeypatch.context() as failure:
        failure.setattr("order_manager.store.os.replace", fail_replace)
        status, _, body = confirm(active_app, "close", journey["id"], interface)
    assert status == 503
    assert "reintentar" in body
    assert "detalle técnico" not in body
    assert store.get_journey() == journey
    assert store.get_globals() == globals_before
    assert store.get_last_export() == export_before
    assert store.global_file.read_bytes() == disk_before
    assert not list(store.global_file.parent.glob("*.tmp"))

    status, _, _ = confirm(active_app, "close", journey["id"], interface)
    assert status == 200
    assert store.get_journey() is None
    assert store.get_globals()["journeys"] == 2
    assert store.get_globals()["revenue"] == 300
    assert Store(store.global_file).get_globals() == store.get_globals()
    assert confirm(active_app, "close", journey["id"], interface)[0] == 409


@pytest.mark.parametrize("action", ["create", "update", "delete"])
@pytest.mark.parametrize("interface", ["ui", "api"])
def test_inventory_failure_is_explained_without_changing_data(
    active_app, monkeypatch, action, interface,
):
    store = active_app.state.store
    original = store.get_inventory()
    journey = store.get_journey()
    disk_before = store.inventory_file.read_bytes()
    article_id = original["articles"][0]["id"]
    values = {"name": "Especial", "category": "Otros", "subcategory": "Casa", "unit_price": 100}

    def fail_write(*_args):
        raise OSError("fallo simulado")

    with monkeypatch.context() as failure:
        failure.setattr(store, "_write_json", fail_write)
        if interface == "ui":
            values["article_id"] = "" if action == "create" else article_id
            values["action"] = "delete" if action == "delete" else "save"
            status, _, body = request(active_app, "POST", "/ui/articles", values, form=True)
        else:
            method = {"create": "POST", "update": "PUT", "delete": "DELETE"}[action]
            path = "/api/articles" + ("" if action == "create" else f"/{article_id}")
            status, _, body = request(active_app, method, path, values)
    assert status == 503
    assert "No se pudo guardar el catálogo" in body
    assert store.get_inventory() == original
    assert store.get_journey() == journey
    assert store.inventory_file.read_bytes() == disk_before
    if interface == "ui" and action != "delete":
        assert 'name="name" value="Especial"' in body
        assert f'name="article_id" value="{values["article_id"]}"' in body


def test_distinct_articles_keep_separate_totals_and_labels(active_app):
    store = active_app.state.store
    author = store.get_journey()["authors"][0]
    identities = [
        ["Bebidas / Casa", "Frías", "Especial"],
        ["Bebidas", "Casa / Frías", "Especial"],
        ["Bebidas", "Casa", "Frías / Especial"],
        ["Bebidas \\/ Casa", "Frías", "Especial"],
    ]
    for index, parts in enumerate(identities, start=1):
        line = dict(zip(("category", "subcategory", "name"), parts))
        store.save_order(author["id"], [{**line, "quantity": index, "unit_price": 100}])
    stats = store.get_summary()
    keys = [article_statistics_key(parts) for parts in identities]
    assert len(stats["by_article"]) == len(identities)
    assert len({article_statistics_label(key) for key in keys}) == len(keys)
    assert '&quot;Bebidas / Casa&quot; / Frías / Especial' in articles_page(store)
    for index, key in enumerate(keys, start=1):
        expected = {"units": index, "revenue": index * 100}
        assert stats["by_article"][key] == expected
        assert stats["by_author"][author["id"]]["by_article"][key] == expected
    exported = json.loads(store.close_journey())
    assert exported["statistics"]["by_article"] == stats["by_article"]
    assert Store(store.global_file).get_globals()["by_article"] == stats["by_article"]


def test_old_statistics_preserve_history_and_merge_unambiguous_articles(tmp_path):
    path = tmp_path / "globals.json"
    legacy = fresh_globals()
    legacy.pop("article_key_format")
    ambiguous = "Bebidas / Casa / Frías / Especial"
    parts = ["Comida", "Minutas", "Milanesa c/guarnicion"]
    old_key = " / ".join(parts)
    legacy["by_article"] = {
        old_key: {"units": 2, "revenue": 200},
        ambiguous: {"units": 5, "revenue": 500},
    }
    legacy.update(journeys=1, orders=2, units=7, revenue=700)
    path.write_text(json.dumps(legacy))
    disk_before = path.read_bytes()
    store = Store(path)
    assert path.read_bytes() == disk_before
    key = article_statistics_key(parts)
    assert store.get_globals()["by_article"][key] == legacy["by_article"][old_key]
    assert store.get_globals()["by_article"][ambiguous] == legacy["by_article"][ambiguous]
    store.create_journey("Nueva")
    author = store.add_author("Ana")
    line = dict(zip(("category", "subcategory", "name"), parts))
    store.save_order(author["id"], [{**line, "quantity": 1, "unit_price": 100}])
    store.close_journey()
    persisted = Store(path).get_globals()
    assert persisted["by_article"][key] == {"units": 3, "revenue": 300}
    assert persisted["by_article"][ambiguous] == legacy["by_article"][ambiguous]
    assert persisted["revenue"] == 800
    assert persisted["article_key_format"] == "escaped-v1"


def test_events_belong_only_to_active_journey_and_export_keeps_closed_events(active_app):
    store = active_app.state.store
    first_events = deepcopy(store.get_events())
    exported = json.loads(store.close_journey())
    assert exported["events"][:-1] == first_events
    assert exported["events"][-1]["action"] == "journey_closed"
    assert json.loads(request(active_app, "GET", "/api/events")[2]) == []
    store.create_journey("Jornada B")
    current_events = store.get_journey()["events"]
    assert store.get_events() == current_events
    assert json.loads(request(active_app, "GET", "/api/events")[2]) == current_events
    page = request(active_app, "GET", "/registros")[2]
    assert "Jornada B" in page and "Jornada A" not in page
    store.discard_journey()
    assert store.get_events() == []
