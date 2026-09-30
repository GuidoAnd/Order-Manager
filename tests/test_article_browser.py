"""Búsqueda, paginación y acceso a las órdenes de artículos temporales."""

from html import unescape
import re

import pytest

from order_manager.api import make_app
from test_review_fixes import request


@pytest.fixture
def app(tmp_path):
    application = make_app(tmp_path / "globals.json")
    application.state.store.create_journey("Turno")
    application.state.store.add_author("Ana")
    return application


def available_rows(page):
    return page.split('id="available-articles"', 1)[1].split("<tbody>", 1)[1].split("</tbody>", 1)[0]


def test_search_pages_are_bounded_stable_and_do_not_modify_data(app):
    store = app.state.store
    before = store.get_journey()
    pages = []
    for number, expected in [(1, 5), (2, 5), (14, 3), (999, 3)]:
        status, _, page = request(app, "GET", f"/articulos?page={number}")
        assert status == 200
        rows = available_rows(page)
        assert rows.count("<tr>") == expected
        pages.append(re.findall(r'name="edit" value="([^"]+)"', rows))
    assert not set(pages[0]) & set(pages[1])
    assert pages[2] == pages[3]
    assert store.get_journey() == before
    assert request(app, "GET", "/articulos?page=0")[0] == 422


def test_name_search_ignores_case_accents_and_spaces(app):
    status, _, page = request(app, "GET", "/articulos?q=%20CAF%C3%89%20")
    assert status == 200
    assert "3 resultados" in page
    assert 'data-label="Nombre">Cafe</td>' in available_rows(page)
    status, _, empty = request(app, "GET", "/articulos?q=ProductoInexistente")
    assert status == 200
    assert "0 resultados" in empty
    assert "No hay artículos que coincidan" in available_rows(empty)
    _, _, escaped = request(app, "GET", "/articulos?q=%22%3E%3Cimg%3E")
    assert "<img>" not in escaped
    assert "&lt;img&gt;" in escaped


def test_category_and_subcategory_filters_and_pagination_links(app):
    status, _, page = request(
        app, "GET", "/articulos?category=Bebidas+con+alcohol&subcategory=Aperitivos",
    )
    assert status == 200
    rows = available_rows(page)
    assert rows.count("<tr>") == 5
    assert rows.count('data-label="Categoría">Bebidas con alcohol') == 5
    assert rows.count('data-label="Subcategoría">Aperitivos') == 5
    assert "category=Bebidas+con+alcohol&amp;subcategory=Aperitivos&amp;page=2" in page


def test_edit_delete_and_validation_preserve_search(app):
    store = app.state.store
    coffee = next(item for item in store.get_available_articles() if item["name"] == "Cafe")
    values = {
        "article_id": coffee["id"], "name": "Cafe", "category": "Cafetería",
        "subcategory": "Infusiones", "unit_price": "bad",
        "q": "café", "filter_category": "Cafetería", "filter_subcategory": "Infusiones",
        "page": "1",
    }
    before = store.get_inventory()
    status, _, page = request(app, "POST", "/ui/articles", values, form=True)
    assert status == 400
    assert 'name="q" value="café"' in page
    assert store.get_inventory() == before
    values["unit_price"] = "3100"
    status, headers, _ = request(app, "POST", "/ui/articles", values, form=True)
    assert status == 303
    assert "q=caf%C3%A9&category=Cafeter%C3%ADa&subcategory=Infusiones&page=1" in headers["location"]
    values["action"] = "delete"
    status, headers, _ = request(app, "POST", "/ui/articles", values, form=True)
    assert status == 303
    _, _, page = request(app, "GET", headers["location"])
    assert "2 resultados" in page
    assert not any(item["id"] == coffee["id"] for item in store.get_inventory()["articles"])


def test_temporary_article_links_only_to_orders_using_its_full_identity(app):
    store = app.state.store
    ana = store.get_journey()["authors"][0]
    bob = store.add_author("Bob")
    line = {
        "name": "Especial", "category": "Otros", "subcategory": "Otros",
        "unit_price": 100, "quantity": 1,
    }
    first = store.save_order(ana["id"], [line])
    second = store.save_order(bob["id"], [{**line, "name": "ESPECIAL", "quantity": 2}])
    store.save_order(ana["id"], [{**line, "category": "Postres", "subcategory": "Golosinas"}])
    _, _, page = request(app, "GET", "/articulos?q=especial&category=Otros")
    rows = available_rows(page)
    assert "Temporal de esta jornada" in rows
    assert 'name="article_id"' not in rows
    link = unescape(re.search(r'href="([^"]+)">Ver órdenes que lo usan', rows).group(1))
    status, _, orders = request(app, "GET", link)
    assert status == 200
    assert "Especial × 1" in orders and "ESPECIAL × 2" in orders
    assert orders.count('name="edit"') == 2
    store.delete_order(first["id"])
    store.delete_order(second["id"])
    status, _, stale = request(app, "GET", link)
    assert status == 200
    assert "El artículo ya no está presente" in stale
    assert 'name="edit"' not in stale


@pytest.mark.parametrize("page_size", [2, 3, 4, 5])
def test_each_responsive_page_size_reaches_every_article_once(app, page_size):
    from dataclasses import replace
    from order_manager.article_search import ArticleSearch

    catalog = app.state.store.get_available_articles()
    search = ArticleSearch()
    _, total, _, pages = search.results(catalog, page_size=page_size)
    seen = []
    for number in range(1, pages + 1):
        rows, found, page, count = replace(search, page=number).results(
            catalog, page_size=page_size,
        )
        assert 0 < len(rows) <= page_size
        assert page == number and found == total and count == pages
        seen.extend(article["id"] for article in rows)
    assert len(seen) == len(set(seen)) == len(catalog)
    assert set(seen) == {article["id"] for article in catalog}


def test_article_form_uses_existing_taxonomy_and_ignores_inactive_fields(app):
    store = app.state.store
    values = {
        "name": "Nuevo café", "category_article": "Cafetería",
        "subcategory_article_3": "Infusiones",
        "subcategory_article_1": "Aguas minerales", "unit_price": "100",
    }
    status, _, _ = request(app, "POST", "/ui/articles", values, form=True)
    assert status == 303
    article = next(item for item in store.get_inventory()["articles"] if item["name"] == "Nuevo café")
    assert article["category"] == "Cafetería"
    assert article["subcategory"] == "Infusiones"
    _, _, page = request(app, "GET", f"/articulos?edit={article['id']}")
    editor = page.split('id="article-editor"', 1)[1]
    assert 'name="category_article"' in editor
    assert 'name="subcategory_article_3"' in editor
    assert 'value="Cafetería" selected' in editor
    assert 'value="Infusiones" selected' in editor
    assert '<input name="category"' not in editor
    assert '<input name="subcategory"' not in editor


@pytest.mark.parametrize("category, subcategory, message", [
    ("Inventada", "Infusiones", "categoría existente"),
    ("Cafetería", "Aguas minerales", "subcategoría de esa categoría"),
    ("Cafetería", "", "subcategoría de esa categoría"),
])
def test_article_form_rejects_unknown_or_mismatched_taxonomy(app, category, subcategory, message):
    store = app.state.store
    before = store.get_inventory()
    values = {
        "name": "Rechazado", "category_article": category,
        "subcategory_article_3": subcategory, "unit_price": "100", "q": "café",
    }
    status, _, page = request(app, "POST", "/ui/articles", values, form=True)
    assert status == 400
    assert message in page
    assert store.get_inventory() == before
    assert 'value="Rechazado"' in page
    assert 'name="q" value="café"' in page
