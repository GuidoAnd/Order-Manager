"""Inventario persistente y resultados separados por autor en v0.2."""

import asyncio
import json

import pytest

from order_manager.api import make_app
from order_manager.article_search import ArticleSearch
from order_manager.seed_inventory import initial_inventory
from order_manager.store import DomainError, Store
from order_manager.web import articles_page, dashboard, journey_page, orders_page


def asgi_json(app, method, path, payload=None):
    body = json.dumps(payload).encode("utf-8") if payload is not None else b""
    messages = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
        "scheme": "http",
        "server": ("test", 80),
        "client": ("test", 1),
        "root_path": "",
    }
    asyncio.run(app(scope, receive, send))
    status = next(
        message["status"] for message in messages
        if message["type"] == "http.response.start"
    )
    response = b"".join(
        message.get("body", b"") for message in messages
        if message["type"] == "http.response.body"
    )
    return status, json.loads(response)


def test_inventory_api_and_unpriced_order_flow(tmp_path):
    app = make_app(tmp_path / "global.json")
    status, inventory = asgi_json(app, "GET", "/api/inventory")
    assert status == 200
    assert len(inventory["articles"]) == 68
    water = next(
        item for item in inventory["articles"]
        if item["name"] == "Agua Villamanaos 600cc"
    )
    assert water["unit_price"] is None

    asgi_json(app, "POST", "/api/journey", {"title": "Tarde"})
    _, author = asgi_json(app, "POST", "/api/authors", {"name": "Ana"})
    status, order = asgi_json(app, "POST", "/api/orders", {
        "author_id": author["id"],
        "lines": [{
            "catalog_id": water["id"],
            "quantity": 3,
            "unit_price": 2500,
        }],
    })
    assert status == 201
    assert order["total"] == 7500
    status, statistics = asgi_json(app, "GET", "/api/statistics/journey")
    assert status == 200
    assert statistics["by_author"][author["id"]]["units"] == 3


def test_initial_inventory_persists_and_unpriced_article_needs_order_price(tmp_path):
    path = tmp_path / "global.json"
    store = Store(path)
    inventory = store.get_inventory()
    assert len(inventory["categories"]) == 7
    assert len(inventory["subcategories"]) == 21
    assert len(inventory["articles"]) == 68
    assert inventory == initial_inventory()
    assert (tmp_path / "inventory.json").exists()

    journey = store.create_journey("Tarde")
    assert len(journey["articles"]) == len(inventory["articles"])
    author = store.add_author("Ana")
    water = next(
        article for article in journey["articles"]
        if article["name"] == "Agua Villamanaos 600cc"
    )
    assert water["unit_price"] is None
    with pytest.raises(DomainError, match="precio"):
        store.save_order(author["id"], [{"catalog_id": water["id"], "quantity": 2}])

    order = store.save_order(author["id"], [{
        "catalog_id": water["id"],
        "quantity": 2,
        "unit_price": 2500,
    }])
    assert order["total"] == 5000
    assert order["lines"][0]["unit_price"] == 2500

    restored = Store(path)
    assert restored.get_inventory() == inventory
    restored.create_journey("Noche")
    assert any(
        article["id"] == water["id"]
        for article in restored.get_journey()["articles"]
    )


def test_catalog_changes_persist_without_changing_existing_orders(tmp_path):
    path = tmp_path / "global.json"
    store = Store(path)
    store.create_journey("Tarde")
    author = store.add_author("Ana")
    coffee = next(
        article for article in store.get_journey()["articles"]
        if article["name"] == "Cafe"
    )
    first = store.save_order(author["id"], [{
        "catalog_id": coffee["id"],
        "quantity": 2,
        "unit_price": 1,
    }])
    assert first["total"] == 5600

    store.update_article(coffee["id"], {
        "name": "Cafe",
        "category": "Cafetería",
        "subcategory": "Infusiones",
        "unit_price": 3100,
    })
    second = store.save_order(author["id"], [{
        "catalog_id": coffee["id"],
        "quantity": 1,
    }])
    assert second["total"] == 3100
    assert store.get_journey()["orders"][0]["lines"][0]["unit_price"] == 2800

    custom = store.add_article({
        "name": "Especial",
        "category": "Comida nueva",
        "subcategory": "Platos",
        "unit_price": None,
    })
    restored = Store(path)
    assert any(item["id"] == custom["id"] for item in restored.get_inventory()["articles"])
    assert any(item["name"] == "Comida nueva" for item in restored.get_inventory()["categories"])
    restored.create_journey("Noche")
    assert next(
        item for item in restored.get_journey()["articles"]
        if item["id"] == coffee["id"]
    )["unit_price"] == 3100


def test_failed_inventory_write_keeps_catalog_intact(tmp_path, monkeypatch):
    store = Store(tmp_path / "global.json")
    store.create_journey("Tarde")
    original = store.get_inventory()

    def fail_write(*_args):
        raise OSError("disk full")

    monkeypatch.setattr(store, "_write_json", fail_write)
    with pytest.raises(DomainError, match="No se pudo guardar el catálogo"):
        store.add_article({
            "name": "Nuevo",
            "category": "Otros",
            "subcategory": "Otros",
            "unit_price": 10,
        })
    assert store.get_inventory() == original
    assert store.get_journey()["articles"] == original["articles"]


def test_order_article_is_reusable_only_while_sold_and_keeps_history(tmp_path):
    path = tmp_path / "global.json"
    store = Store(path)
    store.create_journey("Tarde")
    author = store.add_author("Ana")
    line = {
        "name": "Limonada de la casa",
        "category": "Bebidas sin alcohol",
        "subcategory": "Preparados de la casa",
        "unit_price": 1800,
        "quantity": 2,
    }
    first = store.save_order(author["id"], [line])
    temporary = next(
        article for article in store.get_available_articles()
        if article["name"] == line["name"]
    )
    assert temporary["temporary"] is True
    assert temporary["unit_price"] == 1800
    assert "Limonada de la casa · 1800 · de esta jornada" in orders_page(store)
    assert "Temporal de esta jornada" in articles_page(
        store, search=ArticleSearch(query=line["name"]),
    )
    assert not any(
        article["name"] == line["name"]
        for article in store.get_inventory()["articles"]
    )

    second = store.save_order(author["id"], [{
        "catalog_id": temporary["id"],
        "quantity": 1,
    }])
    assert second["total"] == 1800
    store.delete_order(first["id"])
    assert any(
        article["id"] == temporary["id"]
        for article in store.get_available_articles()
    )

    replacement = {**line, "name": "Jugo de la casa", "quantity": 1}
    store.save_order(author["id"], [replacement], second["id"])
    assert not any(
        article["id"] == temporary["id"]
        for article in store.get_available_articles()
    )
    assert any(
        article["name"] == replacement["name"]
        for article in store.get_available_articles()
    )

    exported = json.loads(store.close_journey())
    assert exported["orders"][0]["lines"][0]["name"] == replacement["name"]
    article_key = "Bebidas sin alcohol / Preparados de la casa / Jugo de la casa"
    assert Store(path).get_globals()["by_article"][article_key]["units"] == 1
    assert not any(
        article["name"] == replacement["name"]
        for article in Store(path).get_inventory()["articles"]
    )


def test_temporary_article_disappears_after_last_order_is_deleted(tmp_path):
    store = Store(tmp_path / "global.json")
    store.create_journey("Tarde")
    author = store.add_author("Ana")
    order = store.save_order(author["id"], [{
        "name": "Agua de los cielos",
        "category": "Bebidas sin alcohol",
        "subcategory": "Aguas minerales",
        "unit_price": 1900,
        "quantity": 1,
    }])
    assert any(
        article["name"] == "Agua de los cielos"
        for article in store.get_available_articles()
    )
    store.delete_order(order["id"])
    assert not any(
        article["name"] == "Agua de los cielos"
        for article in store.get_available_articles()
    )
    assert "Agua de los cielos" not in articles_page(store)


def test_author_views_keep_orders_and_totals_separate(tmp_path):
    store = Store(tmp_path / "global.json")
    store.create_journey("Tarde")
    ana = store.add_author("Ana")
    beto = store.add_author("Beto")

    def line(quantity):
        return {
            "name": "Cafe",
            "category": "Cafetería",
            "subcategory": "Infusiones",
            "unit_price": 100,
            "quantity": quantity,
        }

    store.save_order(ana["id"], [line(2)])
    store.save_order(beto["id"], [line(5)])
    store.save_order(ana["id"], [line(1)])
    stats = store.get_summary()
    assert stats["revenue"] == 800
    assert stats["by_author"][ana["id"]]["revenue"] == 300
    assert stats["by_author"][beto["id"]]["revenue"] == 500
    assert stats["by_author"][ana["id"]]["by_article"][
        "Cafetería / Infusiones / Cafe"
    ]["units"] == 3

    page = journey_page(store)
    ana_section = page.split("<h3>Ana</h3>", 1)[1].split("<h3>Beto</h3>", 1)[0]
    beto_section = page.split("<h3>Beto</h3>", 1)[1].split(
        "<h2>Finalizar jornada</h2>", 1
    )[0]
    assert "#1" in ana_section and "#3" in ana_section
    assert "#2" not in ana_section
    assert "#2" in beto_section and "#1" not in beto_section
    assert "Acumulado del autor" in ana_section
    assert "Artículos facturados por este autor" in ana_section
    assert "Resultados por autor" in dashboard(store)

    grouped = orders_page(store)
    assert "Órdenes por autor" in grouped
    assert 'optgroup label="Cafetería / Infusiones"' in grouped
    assert "precio a completar" in grouped
