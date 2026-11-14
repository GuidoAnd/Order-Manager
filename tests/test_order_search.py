"""Criterios independientes y navegación estable del buscador único de órdenes."""

from html import unescape
import re
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from order_manager.api import make_app
from order_manager.store import Store
from test_order_browser import first_view, numbers
from test_order_navigation import editor, post
from test_review_fixes import request


@pytest.fixture
def catalog(tmp_path):
    app = make_app(data_dir=tmp_path / 'data')
    store = app.state.store
    store.create_journey('Turno')
    authors = [store.add_author('José 2'), store.add_author('Bea')]
    article = next(a for a in store.get_inventory()['articles'] if a['unit_price'] is not None)
    orders = [store.save_order(
        authors[index % 2]['id'], [{'catalog_id': article['id'], 'quantity': 1}],
        series='10', serial_number=2 if index in (0, 2) else index + 10,
    ) for index in range(14)]
    return app, authors, article, orders


def search(app, criterion, query, **extra):
    status, _, html = request(app, 'GET', '/ordenes?' + urlencode({
        'search_by': criterion, 'q': query, **extra,
    }))
    assert status == 200
    assert html.count('class="order-search"') == 1
    assert 'Buscador de Órdenes' in html
    assert f'value="{criterion}" selected' in html
    return html


@pytest.mark.parametrize(('criterion', 'query', 'expected'), [
    ('author', 'JOSE', [1, 3, 5, 7, 9]),
    ('author', '2', [1, 3, 5, 7, 9]),
    ('id', '2', [2]),
    ('id', '#0002', [2]),
    ('id', 'José', []),
    ('serial', '002', [1, 3]),
    ('serial', '#2', []),
    ('serial', '00011', [2]),
    ('serial', 'Bea', []),
    ('all', '#2', [2]),
    ('id', '9' * 200, []),
])
def test_criteria_do_not_mix_identifiers(catalog, criterion, query, expected):
    app, _, _, _ = catalog
    before = app.state.store._state()
    revision = app.state.store.storage.revision
    assert numbers(first_view(search(app, criterion, query))) == expected
    assert app.state.store._state() == before
    assert app.state.store.storage.revision == revision


def test_internal_uuid_is_exact_and_distinct_from_counter(catalog):
    app, _, _, orders = catalog
    assert numbers(first_view(search(app, 'id', orders[3]['id'].upper()))) == [4]
    assert numbers(first_view(search(app, 'id', orders[3]['id'][:8]))) == []


def test_search_escaping_and_empty_criterion(catalog):
    app, _, _, _ = catalog
    html = search(app, 'author', '"><img src=x>')
    assert '<img src=x>' not in html and '&lt;img src=x&gt;' in html
    assert '0 órdenes' in html
    html = search(app, 'serial', '')
    assert '14 órdenes' in html
    status, _, html = request(app, 'GET', '/ordenes?search_by=unknown&q=%232')
    assert status == 200 and numbers(first_view(html)) == [2]
    assert 'value="all" selected' in html


def state_of(url):
    fields = parse_qs(urlsplit(unescape(url) if '&amp;' in url else url).query, keep_blank_values=True)
    return {k: fields[k][0] for k in ('page', 'article', 'q', 'search_by')}


def test_actions_keep_filter_and_page_including_picker_and_errors(catalog):
    app, authors, article, orders = catalog
    state = dict(page='2', article=article['id'], q='JOSE', search_by='author')
    html = search(app, 'author', 'JOSE', page=2, article=article['id'])
    assert numbers(first_view(html)) == [11, 13]
    previous = re.search(r'href="([^"]+)">Anterior', first_view(html)).group(1)
    assert state_of(previous) == {**state, 'page': '1'}
    status, _, html = request(app, 'GET', f'/ordenes/{orders[10]["id"]}/editar?' + urlencode(state))
    assert status == 200
    cancel = re.search(r'href="([^"]+)">Cancelar', html).group(1)
    assert state_of(cancel) == state
    data = editor(app, orders[10]['id'])
    data.update(state, author_id=authors[0]['id'])
    status, headers, _ = post(app, {**data, 'quantity_0': '0'})
    assert status == 303
    status, _, html = request(app, 'GET', headers['location'])
    assert status == 400
    for key, value in state.items():
        assert f'name="{key}" value="{value}"' in html
    data['editor_token'] = re.search(r'name="editor_token" value="([^"]+)"', html).group(1)
    status, headers, _ = post(app, {**data, 'action': 'pick'})
    assert status == 303
    draft_key = urlsplit(headers['location']).path.split('/')[-2]
    assert {k: str(app.state.order_drafts.get(draft_key)['values'][k]) for k in state} == state
    status, headers, _ = post(app, {**data, 'quantity_0': '2'})
    assert status == 303 and state_of(headers['location']) == state
    assert numbers(first_view(request(app, 'GET', headers['location'])[2])) == [11, 13]
    status, headers, _ = request(app, 'POST', '/ui/orders/delete', {
        **state, 'order_id': orders[10]['id'],
    }, form=True)
    assert status == 303 and state_of(headers['location']) == state
    status, _, html = request(app, 'POST', '/ui/orders/delete', {
        **state, 'order_id': 'missing',
    }, form=True)
    assert status == 404 and 'value="author" selected' in html
    assert 'value="JOSE"' in html


def test_edit_keeps_creation_order_and_counter_after_restart(catalog):
    app, authors, article, orders = catalog
    store = app.state.store
    before = store.get_journey()
    html = request(app, 'GET', '/ordenes')[2]
    positions = [numbers(part) for part in html.split('<div class="order-page-size')[1:]]
    data = editor(app, orders[2]['id'])
    assert post(app, {**data, 'quantity_0': '4', 'serial_number': '030'})[0] == 303
    after = store.get_journey()
    assert [o['id'] for o in after['orders']] == [o['id'] for o in before['orders']]
    assert [o['number'] for o in after['orders']] == [o['number'] for o in before['orders']]
    assert after['orders'][2]['created_at'] == before['orders'][2]['created_at']
    assert after['orders'][2]['lines'][0]['quantity'] == 4
    html = request(app, 'GET', '/ordenes')[2]
    assert [numbers(part) for part in html.split('<div class="order-page-size')[1:]] == positions
    recovered = Store(store.global_file)
    assert recovered.get_journey()['orders'] == after['orders']
    changed = store.save_order(authors[1]['id'], [{'catalog_id': article['id'], 'quantity': 2}],
                               orders[2]['id'], series='10', serial_number=30)
    assert changed['number'] == 3
    assert 3 not in numbers(first_view(search(app, 'author', 'JOSE')))
    assert 3 in numbers(first_view(search(app, 'author', 'Bea')))


def test_changed_search_value_can_remove_order_without_deleting_it(catalog):
    app, _, _, orders = catalog
    data = editor(app, orders[0]['id'])
    data.update(search_by='serial', q='002', serial_number='030')
    status, headers, _ = post(app, data)
    assert status == 303
    html = request(app, 'GET', headers['location'])[2]
    assert numbers(first_view(html)) == [3]
    assert len(app.state.store.get_journey()['orders']) == 14
    assert numbers(first_view(search(app, 'id', '#1'))) == [1]


def test_product_search_uses_saved_names_without_duplicates_or_writes(catalog):
    app, authors, _, _ = catalog
    store = app.state.store
    line = dict(name='Té de limón', category='Otros', subcategory='Otros',
                quantity=1, unit_price=100)
    matching = store.save_order(authors[0]['id'], [line, {**line, 'name': 'Té frío'}],
                                series='10', serial_number=40)
    store.save_order(authors[1]['id'], [{**line, 'name': 'Jugo'}],
                     series='10', serial_number=41)
    article = next(a for a in store.get_available_articles() if a['name'] == line['name'])
    store.update_article(article['id'], {**article, 'name': 'Limonada'})
    before = store._state()
    revision = store.storage.revision
    assert numbers(first_view(search(app, 'product', 'TE'))) == [matching['number']]
    assert numbers(first_view(search(app, 'product', 'LIMON'))) == [matching['number']]
    assert numbers(first_view(search(app, 'all', 'limon'))) == [matching['number']]
    assert numbers(first_view(search(app, 'product', 'Limonada'))) == []
    assert numbers(first_view(search(app, 'product', 'José'))) == []
    assert numbers(first_view(search(app, 'product', '<img src=x>'))) == []
    assert store._state() == before and store.storage.revision == revision


def test_product_search_keeps_paging_editor_picker_and_identity_filter(catalog):
    app, _, article, orders = catalog
    state = dict(page='2', article=article['id'], q=article['name'], search_by='product')
    html = search(app, 'product', article['name'], page=2, article=article['id'])
    assert set(numbers(first_view(html))) == {6, 7, 8, 9, 10}
    previous = re.search(r'href="([^"]+)">Anterior', first_view(html)).group(1)
    assert state_of(previous) == {**state, 'page': '1'}
    status, _, html = request(app, 'GET', f'/ordenes/{orders[5]["id"]}/editar?' + urlencode(state))
    assert status == 200
    assert state_of(re.search(r'href="([^"]+)">Cancelar', html).group(1)) == state
    values = {**editor(app, orders[5]['id']), **state, 'author_id': orders[5]['author_id']}
    status, headers, _ = post(app, {**values, 'action': 'pick'})
    assert status == 303
    token = urlsplit(headers['location']).path.split('/')[-2]
    entry = app.state.order_drafts.get(token)
    assert {key: str(entry['values'][key]) for key in state} == state
    status, headers, _ = post(app, {**values, 'quantity_0': '2'})
    assert status == 303 and state_of(headers['location']) == state
    assert set(numbers(first_view(request(app, 'GET', headers['location'])[2]))) == {6, 7, 8, 9, 10}
