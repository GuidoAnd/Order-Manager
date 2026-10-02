"""Regresiones de formularios antiguos, categorías, límites y consultas repetidas."""

import json
import math
from unittest.mock import patch

import pytest

from order_manager.api import make_app
from order_manager.article_search import ArticleSearch
from order_manager.store import MAX_INPUT_INTEGER, DomainError, Store
from test_review_fixes import request


@pytest.fixture
def active(tmp_path):
    app = make_app(tmp_path / "globals.json")
    app.state.store.create_journey("Primera jornada")
    author = app.state.store.add_author("Ana")
    return app, author


def product(**changes):
    return {"name": "Especial", "category": "Otros", "subcategory": "Otros",
            "unit_price": 100, **changes}


@pytest.mark.parametrize("missing_id", [False, True])
@pytest.mark.parametrize("finish", ["close_journey", "discard_journey"])
def test_old_rename_form_preserves_new_journey(active, finish, missing_id):
    app, _ = active
    store = app.state.store
    first = store.get_journey()
    _, _, page = request(app, "GET", "/jornada")
    assert f'name="journey_id" value="{first["id"]}"' in page
    getattr(store, finish)()
    second = store.create_journey("Segunda jornada")
    globals_before = store.get_globals()
    values = {"action": "rename", "title": "Nombre del formulario anterior"}
    if not missing_id:
        values["journey_id"] = first["id"]

    status, _, page = request(app, "POST", "/ui/journey", values, form=True)

    assert status == 409
    assert "La jornada cambió." in page
    assert store.get_journey() == second
    assert store.get_globals() == globals_before
    values["journey_id"] = second["id"]
    assert request(app, "POST", "/ui/journey", values, form=True)[0] == 303
    assert store.get_journey()["title"] == values["title"]


@pytest.mark.parametrize("method", ["POST", "PUT"])
def test_catalog_taxonomy_uses_existing_spelling_and_can_be_edited(active, method):
    app, _ = active
    store = app.state.store
    inventory = store.get_inventory()
    data = product(category="cafetería", subcategory="infusiones")
    url = "/api/articles"
    if method == "PUT":
        url += "/" + inventory["articles"][0]["id"]
    status, _, body = request(app, method, url, data)
    assert status == (201 if method == "POST" else 200)
    article = json.loads(body)
    assert article["category"] == "Cafetería"
    assert article["subcategory"] == "Infusiones"
    assert store.get_inventory()["categories"] == inventory["categories"]
    assert store.get_inventory()["subcategories"] == inventory["subcategories"]
    assert Store(store.global_file).get_inventory() == store.get_inventory()
    _, _, page = request(app, "GET", f"/articulos?edit={article['id']}")
    editor = page.split('id="article-editor"', 1)[1]
    assert 'value="Cafetería" selected' in editor
    assert 'value="Infusiones" selected' in editor
    values = {"article_id": article["id"], "name": article["name"],
              "category_article": "Cafetería", "subcategory_article_3": "Infusiones",
              "unit_price": 200}
    assert request(app, "POST", "/ui/articles", values, form=True)[0] == 303


@pytest.mark.parametrize("category,subcategory", [
    ("Categoría externa", "Grupo externo"),
    ("Cafetería", "Especiales de la API"),
    ("cafetería", "infusiones"),
])
@pytest.mark.parametrize("order_status", ["sale", "not_billed"])
def test_api_order_taxonomy_remains_editable_without_persisting_it(
    active, category, subcategory, order_status,
):
    app, author = active
    store = app.state.store
    before = store.get_inventory()
    disk_before = store.inventory_file.read_bytes()
    line = product(category=category, subcategory=subcategory, quantity=2)
    status, _, body = request(app, "POST", "/api/orders", {
        "author_id": author["id"], "status": order_status, "lines": [line],
    })
    assert status == 201
    original = json.loads(body)
    _, _, page = request(app, "GET", f"/ordenes?edit={original['id']}")
    inventory = store.get_order_inventory(original["id"])
    position, group = next(
        (index, item) for index, item in enumerate(inventory["categories"])
        if item["name"].casefold() == category.casefold()
    )
    sub = next(item for item in inventory["subcategories"]
               if item["category_id"] == group["id"]
               and item["name"].casefold() == subcategory.casefold())
    assert f'value="{group["name"]}" selected' in page
    assert f'value="{sub["name"]}" selected' in page
    values = {
        "action": "save", "count": 1, "order_id": original["id"],
        "author_id": author["id"], "order_status": order_status,
        "source_0": "new", "name_0": line["name"], "category_0": group["name"],
        f"subcategory_0_{position}": sub["name"], "quantity_0": 3,
        "new_unit_price_0": line["unit_price"],
    }
    assert request(app, "POST", "/ui/orders/form", values, form=True)[0] == 303
    updated = store.get_journey()["orders"][0]
    assert updated["id"] == original["id"] and updated["number"] == original["number"]
    assert updated["total"] == (300 if order_status == "sale" else None)
    assert updated["lines"][0]["category"].casefold() == category.casefold()
    assert updated["lines"][0]["subcategory"].casefold() == subcategory.casefold()
    assert store.get_inventory() == before
    assert store.inventory_file.read_bytes() == disk_before
    assert store.get_order_inventory() == before


@pytest.mark.parametrize("value", [MAX_INPUT_INTEGER + 1, 10**400, "9" * 5000],
                         ids=["over_limit", "float_overflow", "conversion_limit"])
@pytest.mark.parametrize("interface", ["api", "ui"])
@pytest.mark.parametrize("field", ["unit_price", "quantity"])
@pytest.mark.parametrize("editing", [False, True])
def test_extreme_order_values_are_rejected_before_mutating_data(
    active, value, interface, field, editing,
):
    app, author = active
    store = app.state.store
    line = product(quantity=2)
    order_id = store.save_order(author["id"], [line])["id"] if editing else ""
    before = store.get_journey()
    line[field] = value
    if interface == "api":
        url = "/api/orders" + (f"/{order_id}" if editing else "")
        status, _, _ = request(app, "PUT" if editing else "POST", url, {
            "author_id": author["id"], "lines": [line],
        })
        assert status == 422
    else:
        values = {"action": "save", "count": 1, "order_id": order_id,
                  "author_id": author["id"], "source_0": "new", "name_0": line["name"],
                  "category_0": "Otros", "subcategory_0_5": "Otros",
                  "quantity_0": line["quantity"], "new_unit_price_0": line["unit_price"]}
        status, _, page = request(app, "POST", "/ui/orders/form", values, form=True)
        assert status == 400 and "Máximo permitido" in page
    assert store.get_journey() == before
    for path in ("/", "/jornada", "/articulos", "/api/statistics/journey"):
        assert request(app, "GET", path)[0] == 200
    assert json.loads(store.close_journey())["orders"] == before["orders"]


@pytest.mark.parametrize("value", [MAX_INPUT_INTEGER + 1, 10**400, "9" * 5000],
                         ids=["over_limit", "float_overflow", "conversion_limit"])
@pytest.mark.parametrize("interface", ["api", "ui"])
@pytest.mark.parametrize("editing", [False, True])
def test_extreme_catalog_prices_preserve_inventory(active, value, interface, editing):
    app, _ = active
    store = app.state.store
    article_id = store.get_inventory()["articles"][0]["id"] if editing else ""
    before = store.get_journey()
    inventory_before = store.get_inventory()
    disk_before = store.inventory_file.read_bytes()
    data = product(unit_price=value)
    if interface == "api":
        url = "/api/articles" + (f"/{article_id}" if editing else "")
        status, _, _ = request(app, "PUT" if editing else "POST", url, data)
        assert status == 422
    else:
        status, _, page = request(app, "POST", "/ui/articles", {
            **data, "article_id": article_id,
        }, form=True)
        assert status == 400 and "Máximo permitido" in page
    assert store.get_journey() == before
    assert store.get_inventory() == inventory_before
    assert store.inventory_file.read_bytes() == disk_before


def test_maximum_values_keep_statistics_and_close_working(active):
    app, author = active
    line = product(quantity=MAX_INPUT_INTEGER, unit_price=MAX_INPUT_INTEGER)
    status, _, body = request(app, "POST", "/api/orders", {
        "author_id": author["id"], "lines": [line] * 50,
    })
    assert status == 201
    total = 50 * MAX_INPUT_INTEGER**2
    assert json.loads(body)["total"] == total
    stats = app.state.store.get_summary()
    assert math.isfinite(stats["by_author"][author["id"]]["average"])
    for path in ("/", "/jornada", "/articulos", "/api/statistics/journey"):
        assert request(app, "GET", path)[0] == 200
    assert json.loads(app.state.store.close_journey())["statistics"]["revenue"] == total


def test_catalog_is_resolved_once_per_order_and_refreshed_after_changes(active):
    app, author = active
    store = app.state.store
    coffee = next(item for item in store.get_available_articles() if item["name"] == "Cafe")
    original = store.save_order(author["id"], [{**product(), "quantity": 1}])
    temporary = next(item for item in store.get_available_articles() if item.get("temporary"))
    lines = [{"catalog_id": coffee["id"], "quantity": 2},
             {"catalog_id": temporary["id"], "quantity": 1}] * 25
    with patch.object(store, "get_available_articles", wraps=store.get_available_articles) as calls:
        order = store.save_order(author["id"], lines)
        assert calls.call_count == 1
    assert order["total"] == 25 * (coffee["unit_price"] * 2 + 100)
    store.update_article(coffee["id"], {**coffee, "unit_price": 3200})
    with patch.object(store, "get_available_articles", wraps=store.get_available_articles) as calls:
        updated = store.save_order(author["id"], lines, order["id"])
        assert calls.call_count == 1
    assert updated["total"] == 25 * (3200 * 2 + 100)
    store.delete_order(original["id"])
    store.delete_order(order["id"])
    before = store.get_journey()
    with pytest.raises(DomainError, match="Artículo no encontrado"):
        store.save_order(author["id"], lines)
    assert store.get_journey() == before


def test_article_search_is_shared_by_views_and_refreshed_each_request(active):
    app, _ = active
    store = app.state.store
    with patch.object(ArticleSearch, "matching", autospec=True,
                      side_effect=ArticleSearch.matching) as calls:
        status, _, page = request(app, "GET", "/articulos?q=Unico")
        assert status == 200 and "0 resultados" in page
        assert calls.call_count == 1
    store.add_article(product(name="Único"))
    with patch.object(ArticleSearch, "matching", autospec=True,
                      side_effect=ArticleSearch.matching) as calls:
        status, _, page = request(app, "GET", "/articulos?q=Unico")
        assert status == 200 and page.count("1 resultado") == 4
        assert calls.call_count == 1
