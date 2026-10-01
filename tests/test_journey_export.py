"""Exportación centrada en altas, precios y ventas de la jornada."""

from copy import deepcopy
import json

import pytest

from order_manager.api import make_app
from order_manager.store import DomainError, Store
from test_review_fixes import request


def setup_store(tmp_path):
    store = Store(tmp_path / "globals.json")
    store.create_journey("Turno")
    author = store.add_author("Ana")
    return store, author


def product(name="Nuevo", price=100):
    return {"name": name, "category": "Otros", "subcategory": "Otros", "unit_price": price}


def test_empty_export_excludes_initial_inventory_and_internal_counter(tmp_path):
    store, _ = setup_store(tmp_path)
    before = store.get_inventory()
    data = json.loads(store.close_journey())
    assert data["export_format"] == "v0.2"
    assert "articles" not in data and "next_order" not in data
    assert data["new_articles"] == [] and data["price_changes"] == []
    assert data["orders"] == [] and data["statistics"]["revenue"] == 0
    assert store.get_inventory() == before
    assert data["events"][-1]["action"] == "journey_closed"


def test_price_history_preserves_the_prices_sold_in_each_order(tmp_path):
    store, author = setup_store(tmp_path)
    cafe = next(item for item in store.get_available_articles() if item["name"] == "Cafe")
    first = store.save_order(author["id"], [{"catalog_id": cafe["id"], "quantity": 2}])
    store.update_article(cafe["id"], {**cafe, "unit_price": 3100})
    second = store.save_order(author["id"], [{"catalog_id": cafe["id"], "quantity": 3}])
    store.update_article(cafe["id"], cafe)
    data = json.loads(store.close_journey())
    assert data["new_articles"] == []
    assert [(item["previous_price"], item["new_price"]) for item in data["price_changes"]] == [
        (cafe["unit_price"], 3100), (3100, cafe["unit_price"]),
    ]
    assert all(item["at"] and item["article_id"] == cafe["id"] for item in data["price_changes"])
    assert data["orders"] == [first, second]
    assert data["statistics"]["revenue"] == first["total"] + second["total"]


def test_new_articles_include_unsold_catalog_and_current_temporary_products(tmp_path):
    store, author = setup_store(tmp_path)
    catalog = store.add_article(product("Nuevo catálogo"))
    removed = store.add_article(product("Alta eliminada"))
    store.update_article(catalog["id"], product("Nuevo catálogo", 200))
    store.delete_article(removed["id"])
    store.save_order(author["id"], [{**product("Temporal"), "quantity": 3}])
    deleted_order = store.save_order(author["id"], [{**product("Temporal eliminado"), "quantity": 1}])
    store.delete_order(deleted_order["id"])
    data = json.loads(store.close_journey())
    articles = {item["name"]: item for item in data["new_articles"]}
    assert set(articles) == {"Nuevo catálogo", "Alta eliminada", "Temporal"}
    assert articles["Nuevo catálogo"]["unit_price"] == 200
    assert not articles["Nuevo catálogo"]["temporary"]
    assert articles["Alta eliminada"]["deleted"]
    assert articles["Temporal"]["temporary"] and not articles["Temporal"]["deleted"]


def test_renamed_or_deleted_initial_article_is_not_reported_as_new(tmp_path):
    store, author = setup_store(tmp_path)
    initial = next(item for item in store.get_available_articles() if item["name"] == "Cafe")
    store.save_order(author["id"], [{"catalog_id": initial["id"], "quantity": 1}])
    store.update_article(initial["id"], {**initial, "name": "Café renombrado"})
    store.save_order(author["id"], [{"catalog_id": initial["id"], "quantity": 1}])
    store.delete_article(initial["id"])
    data = json.loads(store.close_journey())
    assert data["new_articles"] == [] and data["price_changes"] == []
    assert [order["lines"][0]["name"] for order in data["orders"]] == ["Cafe", "Café renombrado"]


def test_missing_prices_zero_and_unchanged_price(tmp_path):
    store, author = setup_store(tmp_path)
    article = store.add_article(product(price=None))
    store.save_order(author["id"], [{"catalog_id": article["id"], "unit_price": 123, "quantity": 1}])
    store.update_article(article["id"], product(price=0))
    store.update_article(article["id"], product(price=0))
    store.update_article(article["id"], product(price=None))
    data = json.loads(store.close_journey())
    assert [(item["previous_price"], item["new_price"]) for item in data["price_changes"]] == [
        (None, 0), (0, None),
    ]
    assert data["orders"][0]["lines"][0]["unit_price"] == 123


@pytest.mark.parametrize("action", ["create", "update"])
def test_failed_inventory_write_does_not_add_export_activity(tmp_path, monkeypatch, action):
    store, _ = setup_store(tmp_path)
    initial = store.get_available_articles()[0]
    before = deepcopy(store.get_journey())

    def fail(_data):
        raise DomainError("Fallo de escritura", 503)

    with monkeypatch.context() as patch:
        patch.setattr(store, "_write_inventory", fail)
        with pytest.raises(DomainError):
            if action == "create":
                store.add_article(product())
            else:
                store.update_article(initial["id"], {**initial, "unit_price": 777})
    assert store.get_journey() == before
    data = json.loads(store.close_journey())
    assert data["new_articles"] == [] and data["price_changes"] == []


def test_failed_close_keeps_changes_for_retry_and_new_journey_resets_them(tmp_path, monkeypatch):
    store, author = setup_store(tmp_path)
    article = store.add_article(product())
    store.update_article(article["id"], product(price=200))
    store.save_order(author["id"], [{"catalog_id": article["id"], "quantity": 1}])
    before = deepcopy(store.get_journey())

    def fail(_data):
        raise DomainError("Fallo de escritura", 503)

    with monkeypatch.context() as patch:
        patch.setattr(store, "_write_globals", fail)
        with pytest.raises(DomainError):
            store.close_journey()
    assert store.get_journey() == before
    data = json.loads(store.close_journey())
    assert len(data["new_articles"]) == len(data["price_changes"]) == 1
    assert store.get_globals()["journeys"] == 1
    store.create_journey("Siguiente")
    data = json.loads(store.close_journey())
    assert data["new_articles"] == [] and data["price_changes"] == []


def test_discard_resets_activity_and_json_download_matches_the_export(tmp_path):
    app = make_app(tmp_path / "globals.json")
    store = app.state.store
    store.create_journey("Descartada")
    store.add_article(product())
    store.discard_journey()
    journey = store.create_journey("Exportada")
    author = store.add_author("Ana")
    first = store.save_order(author["id"], [{**product("Temporal", 100), "quantity": 1}])
    second = store.save_order(author["id"], [{**product("Temporal", 200), "quantity": 2}])
    payload = store.close_journey()
    status, headers, downloaded = request(app, "GET", f"/api/exports/last?journey_id={journey['id']}")
    assert status == 200 and headers["content-type"] == "application/json"
    assert downloaded.encode() == payload
    data = json.loads(downloaded)
    assert data["price_changes"] == []
    assert len(data["new_articles"]) == 1
    assert data["new_articles"][0]["name"] == "Temporal"
    assert data["orders"] == [first, second]
