"""Regresiones de catálogo recuperado, navegación y consultas por operación."""

from html import unescape
import json
import re
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

import pytest

from order_manager.api import make_app
from order_manager import journey_results, store as store_module
from order_manager.store import Store
from test_review_fixes import request


@pytest.fixture
def recovered_app(tmp_path):
    app = make_app(data_dir=tmp_path / "data")
    store = app.state.store
    store.create_journey("Anterior")
    author = store.add_author("Ana")
    original = store.get_inventory()["articles"][0]
    store.update_article(original["id"], {**original, "unit_price": 100})
    store.save_order(author["id"], [{"catalog_id": original["id"], "quantity": 2}])
    store.close_journey()
    store.create_journey("Posterior")
    updated = store.update_article(original["id"], {**original, "name": "Nombre vigente", "unit_price": 300})
    added = store.add_article({"name": "Alta posterior", "category": "Otros",
                               "subcategory": "Otros", "unit_price": 450})
    info = store.recovery_info()
    store.recover_journey(info["close_id"], info["revision"], info["active_id"])
    yield app, updated, added
    store.runtime_log.close()


@pytest.mark.parametrize("which", [1, 2])
def test_recovered_catalog_editor_uses_current_inventory(recovered_app, which):
    app = recovered_app[0]
    article = recovered_app[which]
    store = app.state.store
    before = store._state()
    status, _, html = request(app, "GET", "/articulos?edit=" + article["id"])
    assert status == 200
    assert f'name="name" value="{article["name"]}"' in html
    price = re.search(r'name="unit_price"[^>]*value="([^"]*)"', html)[1]
    assert price == str(article["unit_price"])
    assert store._state() == before
    status, _, _ = request(app, "POST", "/ui/articles", {
        "article_id": article["id"], "name": article["name"],
        "category": article["category"], "subcategory": article["subcategory"],
        "unit_price": price,
    }, form=True)
    assert status == 303
    assert store.get_journey()["orders"] == before["journey"]["data"]["orders"]
    restarted = Store(store.global_file)
    try:
        assert next(a for a in restarted.get_inventory()["articles"]
                    if a["id"] == article["id"]) == article
        assert restarted.get_journey()["orders"][0]["total"] == 200
    finally:
        restarted.runtime_log.close()


@pytest.mark.parametrize("path", ["/articulos?edit=missing", "/ordenes/missing/editar"])
def test_missing_editor_reports_not_found_without_storage_warning(recovered_app, path):
    app = recovered_app[0]
    before = app.state.store._state()
    status, _, html = request(app, "GET", path)
    assert status == 404
    assert "no encontrad" in html
    assert "Almacenamiento no disponible" not in html
    assert app.state.store._state() == before


def test_journey_navigation_omits_default_pages_and_keeps_other_selections(tmp_path):
    app = make_app(data_dir=tmp_path)
    authors = [{"id": str(i).zfill(36), "name": f"Autor {i}"} for i in range(60)]
    state = {kind: {a["id"]: 1 for a in authors}
             for kind in ("orders", "subtotals", "articles")}
    state["articles"][authors[1]["id"]] = 3
    try:
        html = journey_results._navigation(authors[0], "orders", 1, 2, state)
        url = unescape(re.search(r'href="([^"]+)"', html)[1])
        assert request(app, "GET", url)[0] == 200
        assert parse_qs(urlsplit(url).query) == {
            f'orders_{authors[0]["id"]}': ["2"],
            f'articles_{authors[1]["id"]}': ["3"],
        }
        state["orders"][authors[0]["id"]] = 2
        back = journey_results._navigation(authors[0], "orders", 2, 2, state)
        url = unescape(re.search(r'href="([^"]+)"', back)[1])
        assert parse_qs(urlsplit(url).query) == {f'articles_{authors[1]["id"]}': ["3"]}
    finally:
        app.state.store.runtime_log.close()


def test_catalog_page_reads_one_current_copy_and_refreshes_next_request(recovered_app):
    app, article, _ = recovered_app
    store = app.state.store
    with patch.object(store, "get_inventory", wraps=store.get_inventory) as inventory:
        with patch.object(store, "get_available_articles", wraps=store.get_available_articles) as available:
            assert request(app, "GET", "/articulos?edit=" + article["id"])[0] == 200
    assert inventory.call_count == 1
    assert available.call_count == 0
    store.update_article(article["id"], {**article, "unit_price": 725})
    html = request(app, "GET", "/articulos?edit=" + article["id"])[2]
    assert re.search(r'name="unit_price"[^>]*value="725"', html)


def test_records_read_history_once_after_recovery(recovered_app):
    app = recovered_app[0]
    store = app.state.store
    with patch.object(store, "get_events", wraps=store.get_events) as history:
        status, _, html = request(app, "GET", "/registros")
    assert status == 200
    assert "cuando vuelva a cerrarse" in html
    assert history.call_count == 1


def test_order_catalog_identity_lookup_is_linear_and_registers_new_items(recovered_app):
    app = recovered_app[0]
    store = app.state.store
    catalog = store.get_inventory()["articles"]
    author = store.get_journey()["authors"][0]
    rows = [{"name": "Producto repetido", "category": "Otros", "subcategory": "Otros",
             "quantity": 1, "unit_price": 12} for _ in range(50)]
    with patch.object(store_module, "article_identity", wraps=store_module.article_identity) as identity:
        order = store.save_order(author["id"], rows)
    assert identity.call_count <= len(catalog) + 2 * len(rows) + 2
    assert order["total"] == 600
    matches = [a for a in store.get_inventory()["articles"] if a["name"] == "Producto repetido"]
    assert len(matches) == 1
    store.delete_article(matches[0]["id"])
    # Editar historia no recrea artículos eliminados; una orden nueva sí los incorpora.
    store.save_order(author["id"], rows, order["id"])
    assert not any(a["name"] == "Producto repetido" for a in store.get_inventory()["articles"])
    store.save_order(author["id"], rows)
    assert sum(a["name"] == "Producto repetido" for a in store.get_inventory()["articles"]) == 1


@pytest.mark.parametrize("change", ["reorder", "remove", "deleted"])
def test_api_edit_preserves_historical_prices_when_lines_move(tmp_path, change):
    app = make_app(data_dir=tmp_path)
    store = app.state.store
    try:
        store.create_journey("Históricos")
        author = store.add_author("Ana")
        articles = store.get_inventory()["articles"][:2]
        for index, article in enumerate(articles, start=1):
            store.update_article(article["id"], {**article, "unit_price": index * 100})
        lines = [{"catalog_id": article["id"], "quantity": 1} for article in articles]
        order = store.save_order(author["id"], lines, series="10", serial_number=1)
        for article in articles:
            store.update_article(article["id"], {**article, "name": "Nombre nuevo", "unit_price": 900})
        if change == "deleted":
            store.delete_article(articles[1]["id"])
        moved = list(reversed(lines)) if change == "reorder" else lines[1:]
        status, _, body = request(app, "PUT", "/api/orders/" + order["id"], {
            "author_id": author["id"], "lines": moved,
        })
        assert status == 200
        updated = json.loads(body)
        expected = list(reversed(order["lines"])) if change == "reorder" else order["lines"][1:]
        assert updated["lines"] == expected
        assert updated["id"] == order["id"] and updated["number"] == order["number"]
        assert updated["total"] == sum(line["subtotal"] for line in expected)
        explicit = [{**moved[0], "unit_price": 350}]
        status, _, body = request(app, "PUT", "/api/orders/" + order["id"], {
            "author_id": author["id"], "lines": explicit,
        })
        assert status == 200 and json.loads(body)["total"] == 350
    finally:
        store.runtime_log.close()


def test_added_duplicate_catalog_line_uses_current_price(tmp_path):
    store = Store(tmp_path / "global_stats.json")
    try:
        store.create_journey("Precios")
        author = store.add_author("Ana")
        article = store.get_inventory()["articles"][0]
        store.update_article(article["id"], {**article, "unit_price": 100})
        line = {"catalog_id": article["id"], "quantity": 1}
        order = store.save_order(author["id"], [line])
        store.update_article(article["id"], {**article, "unit_price": 300})
        changed = store.save_order(author["id"], [line, line], order["id"])
        assert [row["unit_price"] for row in changed["lines"]] == [100, 300]
        store.update_article(article["id"], {**article, "unit_price": 500})
        unchanged = store.save_order(author["id"], [line, line], order["id"])
        assert unchanged["lines"] == changed["lines"]
    finally:
        store.runtime_log.close()


def test_duplicate_line_ids_preserve_prices_after_move_restart_and_recovery(tmp_path):
    app = make_app(data_dir=tmp_path)
    store = app.state.store
    restarted = None
    try:
        store.create_journey("Líneas repetidas")
        author = store.add_author("Ana")
        article = store.get_inventory()["articles"][0]
        store.update_article(article["id"], {**article, "unit_price": 100})
        row = {"catalog_id": article["id"], "quantity": 1}
        order = store.save_order(author["id"], [row])
        store.update_article(article["id"], {**article, "unit_price": 300})
        order = store.save_order(author["id"], [row, row], order["id"])
        assert len({line["line_id"] for line in order["lines"]}) == 2
        store.update_article(article["id"], {**article, "unit_price": 900})
        store.delete_article(article["id"])
        moved = [{"catalog_id": article["id"], "quantity": line["quantity"],
                  "line_id": line["line_id"]} for line in reversed(order["lines"])]
        status, _, body = request(app, "PUT", "/api/orders/" + order["id"], {
            "author_id": author["id"], "lines": moved,
        })
        assert status == 200
        assert json.loads(body)["lines"] == list(reversed(order["lines"]))
        restarted = Store(store.global_file)
        assert restarted.get_journey()["orders"] == store.get_journey()["orders"]
        export = json.loads(store.close_journey())
        assert export["orders"][0]["lines"] == list(reversed(order["lines"]))
        info = store.recovery_info()
        store.recover_journey(info["close_id"], info["revision"], info["active_id"])
        changed = store.save_order(author["id"], [moved[0]], order["id"])
        assert changed["lines"] == [order["lines"][1]]
    finally:
        store.runtime_log.close()
        if restarted:
            restarted.runtime_log.close()


@pytest.mark.parametrize("invalid", ["foreign", "duplicate"])
def test_invalid_line_identifiers_do_not_modify_state(tmp_path, invalid):
    app = make_app(data_dir=tmp_path)
    store = app.state.store
    try:
        store.create_journey("Referencias")
        author = store.add_author("Ana")
        article = store.get_inventory()["articles"][0]
        row = {"catalog_id": article["id"], "quantity": 1, "unit_price": 1}
        order = store.save_order(author["id"], [row])
        line = {**row, "line_id": "foreign" if invalid == "foreign" else order["lines"][0]["line_id"]}
        before = store._state()
        status, _, _ = request(app, "PUT", "/api/orders/" + order["id"], {
            "author_id": author["id"], "lines": [line] if invalid == "foreign" else [line, line],
        })
        assert status == (409 if invalid == "foreign" else 400)
        assert store._state() == before
    finally:
        store.runtime_log.close()


def test_new_duplicate_before_identified_line_uses_current_price(tmp_path):
    store = Store(tmp_path / "global_stats.json")
    try:
        store.create_journey("Inserción")
        author = store.add_author("Ana")
        article = store.get_inventory()["articles"][0]
        row = {"catalog_id": article["id"], "quantity": 1}
        store.update_article(article["id"], {**article, "unit_price": 100})
        order = store.save_order(author["id"], [row])
        store.update_article(article["id"], {**article, "unit_price": 300})
        old = {**row, "line_id": order["lines"][0]["line_id"]}
        changed = store.save_order(author["id"], [row, old], order["id"])
        assert [line["unit_price"] for line in changed["lines"]] == [300, 100]
        assert changed["lines"][1] == order["lines"][0]
    finally:
        store.runtime_log.close()


def test_navigation_token_bounds_url_and_preserves_all_selections(tmp_path):
    from order_manager.journey_navigation import JourneyNavigation
    app = make_app(data_dir=tmp_path)
    store = app.state.store
    try:
        store.create_journey("Páginas")
        authors = [{"id": str(i).zfill(36), "name": str(i)} for i in range(300)]
        values = {kind: {a["id"]: 2 for a in authors}
                  for kind in ("orders", "articles", "subtotals")}
        navigation = app.state.journey_navigation
        state = journey_results.NavigationPages(values, navigation, store.get_journey()["id"])
        html = journey_results._navigation(authors[0], "orders", 2, 3, state)
        urls = [unescape(url) for url in re.findall(r'href="([^"]+)"', html)]
        assert len(urls) == 2 and all(len(url) < 200 for url in urls)
        for url, target in zip(urls, (1, 3)):
            query = parse_qs(urlsplit(url).query)
            restored = navigation.load(query["pages"][0], store.get_journey()["id"])
            assert len(restored) == 900
            restored.update({key: value[0] for key, value in query.items() if key != "pages"})
            assert journey_results.page_values(restored, "orders")[authors[0]["id"]] == target
            assert journey_results.page_values(restored, "articles") == values["articles"]
            assert request(app, "GET", url)[0] == 200
        assert len(navigation._entries) == 1
        before = store._state()
        assert "caducó" in request(app, "GET", "/jornada?pages=missing")[2]
        assert store._state() == before
        assert JourneyNavigation().load(state.token, store.get_journey()["id"]) is None
    finally:
        store.runtime_log.close()


def test_navigation_expiration_capacity_and_journey_scope():
    from order_manager.journey_navigation import JourneyNavigation
    navigation = JourneyNavigation()
    navigation.max_entries = 2
    navigation.max_selections = 3
    first = navigation.save("one", {"orders_a": 2})
    assert navigation.load(first, "two") is None
    second = navigation.save("one", {"orders_b": 2})
    assert navigation.load(first, "one") == {"orders_a": 2}
    third = navigation.save("one", {"orders_c": 2, "orders_d": 2})
    assert navigation.load(second, "one") is None
    assert navigation.load(third, "one") == {"orders_c": 2, "orders_d": 2}
    with patch("order_manager.journey_navigation.monotonic", return_value=10**20):
        assert navigation.load(first, "one") is None
        assert navigation.load(third, "one") is None


def test_legacy_order_form_assigns_stable_identifiers_on_first_edit(tmp_path):
    from order_manager.order_lines import line_identifier
    app = make_app(data_dir=tmp_path)
    store = app.state.store
    try:
        store.create_journey("Compatibilidad")
        author = store.add_author("Ana")
        rows = [{"name": "Anterior", "category": "Otros", "subcategory": "Otros",
                 "quantity": 1, "unit_price": price} for price in (100, 300)]
        order = store.save_order(author["id"], rows, series="10", serial_number=1)
        # Simula el formato válido de una orden anterior a los identificadores.
        saved = store.journey["orders"][0]
        for line in saved["lines"]:
            line.pop("line_id")
        before = store._state()
        url = "/ordenes/" + order["id"] + "/editar"
        html = request(app, "GET", url)[2]
        ids = re.findall(r'name="line_id_\d+" value="([^"]+)"', html)
        assert ids == [line_identifier(order["id"], i, line) for i, line in enumerate(saved["lines"])]
        assert request(app, "GET", url)[2] == html
        assert store._state() == before
        changed = store.save_order(author["id"], [{**rows[1], "line_id": ids[1]}], order["id"])
        assert changed["lines"][0]["line_id"] == ids[1]
        restarted = Store(store.global_file)
        try:
            assert restarted.get_journey()["orders"][0] == changed
        finally:
            restarted.runtime_log.close()
    finally:
        store.runtime_log.close()
