"""Distribución compartida por autor y búsqueda con nombres numéricos."""

import pytest

from order_manager.api import make_app
from order_manager.web import _shared_order_pages
from test_order_browser import first_view, numbers
from test_review_fixes import request


@pytest.mark.parametrize("size", [2, 3, 4, 5])
def test_shared_pages_reserve_one_order_for_every_remaining_author(size):
    authors = [{"id": str(n), "name": str(n)} for n in range(7)]
    orders = [{"id": str(n), "number": n, "author_id": str(author)}
              for n, author in enumerate([0] * 12 + [1] * 3 + list(range(2, 7)), 1)]
    pages = _shared_order_pages(orders, authors, size)
    remaining = list(orders)
    seen = []
    for page in pages:
        active = {order["author_id"] for order in remaining}
        assert {order["author_id"] for order in page} == active
        assert len(page) <= max(size, len(active))
        seen.extend(order["number"] for order in page)
        selected = {order["id"] for order in page}
        remaining = [order for order in remaining if order["id"] not in selected]
    assert len(seen) == len(set(seen)) == len(orders)
    assert not remaining
    assert _shared_order_pages([], authors, size) == [[]]


@pytest.mark.parametrize("author_name,query", [("90", "90"), ("90 Ana", "90"),
                                                ("9vidas", "9"), ("123 aa", "123 aa")])
def test_numeric_author_search_keeps_five_results_and_exact_number_mode(tmp_path, author_name, query):
    app = make_app(tmp_path / "globals.json")
    store = app.state.store
    store.create_journey("Turno")
    author = store.add_author(author_name)
    for _ in range(7):
        store.save_order(author["id"], [{"name": "Especial", "category": "Otros",
                                       "subcategory": "Otros", "unit_price": 100,
                                       "quantity": 1}])
    from urllib.parse import urlencode

    _, _, html = request(app, "GET", "/ordenes?" + urlencode({"q": query}))
    assert "7 órdenes" in html
    assert numbers(first_view(html)) == [1, 2, 3, 4, 5]
    assert html.count('class="order-page-size') == 1
    _, _, html = request(app, "GET", "/ordenes?" + urlencode({"q": query, "page": 2}))
    assert numbers(first_view(html)) == [6, 7]
    _, _, html = request(app, "GET", "/ordenes?q=%2390")
    assert not numbers(html)
