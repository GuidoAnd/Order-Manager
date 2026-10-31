"""Selección conjunta, conservación del borrador y navegación móvil sin JavaScript."""

import asyncio
import re

import pytest
from playwright.async_api import async_playwright

from order_manager.article_search import ArticleSearch
from order_manager.store import Store
from test_mobile import VIEWPORTS, assert_layout, serve_asgi
from test_order_navigation import app, confirmed, create, editor, post
from test_review_fixes import request
from test_security import form


PATH = '/ui/orders/articles'


def key_from(response):
    assert response[0] == 303
    return re.search(r'/borrador/([^/]+)', response[1]['location']).group(1)


def open_picker(app, values=None, target=None):
    values = values or editor(app)
    response = post(app, {**values, 'action': 'pick' if target is None else f'pick_{target}'})
    return key_from(response)


def submit(app, key, *, action='search', size=5, changes=None):
    entry = app.state.order_drafts.get(key)
    picker = entry['picker']
    search = ArticleSearch(picker['query'], picker['category'], picker['subcategory'], picker['page'])
    visible = search.results(entry['session']['context']['inventory']['articles'], page_size=size)[0]
    values = dict(editor_token=key, page_size=str(size), action=action, search_q=picker['query'],
                  category=picker['category'], subcategory=picker['subcategory'])
    for article in visible:
        article_id = article['id']
        if article_id in picker['selected']:
            values['selected_' + article_id if picker['target'] is None else 'selected_id'] = (
                '1' if picker['target'] is None else article_id)
        values['amount_' + article_id] = picker['selected'].get(article_id, '1')
    values.update(changes or {})
    return request(app, 'POST', PATH, values, form=True)


def choose(app, key, article, amount='1', *, apply=False):
    key = key_from(submit(app, key, changes={'search_q': article['name']}))
    picker = app.state.order_drafts.get(key)['picker']
    selected = 'selected_' + article['id'] if picker['target'] is None else 'selected_id'
    value = '1' if picker['target'] is None else article['id']
    return submit(app, key, action='apply' if apply else 'keep', changes={
        selected: value, 'amount_' + article['id']: amount})


def form_values(app, key):
    entry = app.state.order_drafts.get(key)
    values = {**entry['values'], 'editor_token': key, 'action': 'save', 'count': str(len(entry['rows']))}
    for index, row in enumerate(entry['rows']):
        for field in ('source', 'catalog_id', 'line_id', 'name', 'category', 'quantity', 'unit_price', 'new_unit_price'):
            values[f'{field}_{index}'] = row.get(field, '')
        for position, name in row.get('subcategories', {}).items():
            values[f'subcategory_{index}_{position}'] = name
    return values


def test_batch_search_keeps_selection_and_editor_fields_without_business_writes(app):
    values = editor(app)
    values.update(quantity_0='7', unit_price_0='25', order_status='not_billed', q='Ana', page='3',
                  count='2', source_1='new', name_1='Producto pendiente', category_1='Otros', quantity_1='4',
                  new_unit_price_1='150')
    before = confirmed(app)
    key = open_picker(app, values)
    original_key = key
    articles = sorted(app.state.store.get_available_articles(), key=lambda a: a['name'])[:2]
    key = key_from(choose(app, key, articles[0], '2'))
    key = key_from(choose(app, key, articles[1], '3'))
    selected = app.state.order_drafts.get(key)['picker']['selected']
    assert selected == {articles[0]['id']: '2', articles[1]['id']: '3'}
    result = submit(app, key, action='apply')
    result_key = key_from(result)
    entry = app.state.order_drafts.get(result_key)
    assert len(entry['rows']) == 4
    assert entry['rows'][0]['quantity'] == '7' and entry['rows'][0]['unit_price'] == '25'
    assert entry['rows'][1]['name'] == 'Producto pendiente'
    assert [(row['catalog_id'], row['quantity']) for row in entry['rows'][2:]] == [
        (articles[0]['id'], '2'), (articles[1]['id'], '3')]
    assert entry['values']['order_status'] == 'not_billed' and entry['values']['page'] == 3
    assert confirmed(app) == before
    assert submit(app, key, action='apply')[:2] == result[:2]
    assert submit(app, original_key, action='apply')[:2] == result[:2]
    assert request(app, 'GET', f'/ordenes/borrador/{key}/articulos')[1]['location'] == result[1]['location']
    assert confirmed(app) == before
    assert Store(app.state.store.global_file).get_journey()['orders'] == []


def test_selection_survives_pages_filters_and_unchecking(app):
    key = open_picker(app)
    inventory = app.state.order_drafts.get(key)['session']['context']['inventory']
    articles = ArticleSearch().results(inventory['articles'], page_size=2)[0]
    first = articles[0]
    key = key_from(submit(app, key, size=2, action='next', changes={
        'selected_' + first['id']: '1', 'amount_' + first['id']: '4'}))
    assert app.state.order_drafts.get(key)['picker']['page'] == 2
    key = key_from(submit(app, key, size=2, changes={'category': first['category'], 'subcategory': first['subcategory']}))
    assert app.state.order_drafts.get(key)['picker']['selected'][first['id']] == '4'
    key = key_from(submit(app, key, size=2, changes={'category': '', 'subcategory': '', 'search_q': first['name']}))
    key = key_from(submit(app, key, size=2, action='keep', changes={'selected_' + first['id']: ''}))
    assert first['id'] not in app.state.order_drafts.get(key)['picker']['selected']


def test_cancel_selection_restores_editor_and_read_only_get(app):
    values = editor(app)
    values.update(quantity_0='6', serial_number='07', unit_price_0='123')
    key = open_picker(app, values)
    before = confirmed(app)
    for _ in range(2):
        status, headers, html = request(app, 'GET', f'/ordenes/borrador/{key}/articulos')
        assert status == 200 and headers['cache-control'] == 'no-store'
        assert f'href="/ordenes/borrador/{key}"' in html
    status, _, html = request(app, 'GET', '/ordenes/borrador/' + key)
    assert status == 200 and 'value="6"' in html and 'value="07"' in html and 'value="123"' in html
    assert confirmed(app) == before


def test_blank_placeholder_reused_and_successful_order_replays_cannot_duplicate(app):
    values = editor(app)
    values['catalog_id_0'] = ''
    key = open_picker(app, values)
    article = next(a for a in app.state.store.get_available_articles() if a['unit_price'] is not None)
    response = choose(app, key, article, '4', apply=True)
    key = key_from(response)
    assert len(app.state.order_drafts.get(key)['rows']) == 1
    assert post(app, form_values(app, key))[0] == 303
    before = confirmed(app)
    assert post(app, form_values(app, key))[0] == 303
    assert confirmed(app) == before
    order = Store(app.state.store.global_file).get_journey()['orders'][0]
    assert order['lines'][0]['quantity'] == 4


@pytest.mark.parametrize('same', [True, False])
def test_replace_keeps_other_lines_and_only_preserves_price_for_same_article(app, same):
    order = create(app)
    values = editor(app, order['id'])
    values.update(quantity_0='8', unit_price_0='123', line_id_0=order['lines'][0]['line_id'],
                  count='2', source_1='new', name_1='Pendiente', quantity_1='2')
    key = open_picker(app, values, target=0)
    articles = app.state.store.get_available_articles()
    article = next(a for a in articles if (a['id'] == values['catalog_id_0']) == same)
    key = key_from(choose(app, key, article, '3', apply=True))
    rows = app.state.order_drafts.get(key)['rows']
    assert len(rows) == 2 and rows[1]['name'] == 'Pendiente'
    assert rows[0]['catalog_id'] == article['id'] and rows[0]['quantity'] == '3'
    if same:
        assert rows[0]['unit_price'] == '123' and rows[0]['line_id'] == order['lines'][0]['line_id']
    else:
        assert not rows[0].get('unit_price') and not rows[0].get('line_id')


@pytest.mark.parametrize('amount', ['0', '-1', '1.2', 'abc', str(2**63)])
def test_invalid_quantity_is_recoverable_without_changing_confirmed_order(app, amount):
    key = open_picker(app)
    article = app.state.store.get_available_articles()[0]
    key = key_from(choose(app, key, article, amount, apply=True))
    entry = app.state.order_drafts.get(key)
    assert entry['status'] == 400 and entry['picker']['selected'][article['id']] == amount
    assert request(app, 'GET', f'/ordenes/borrador/{key}/articulos')[0] == 400
    assert entry['session']['result'] == '' and entry['picker']['flow']['result'] == ''
    assert app.state.store.get_journey()['orders'] == []


def test_empty_forged_selection_and_invalid_page_are_rejected(app):
    key = open_picker(app)
    before = confirmed(app)
    for changes in ({}, {'selected_unknown': '1'}, {'page_size': '100'}):
        failed = key_from(submit(app, key, action='apply', changes=changes))
        assert app.state.order_drafts.get(failed)['status'] == 400
        assert confirmed(app) == before


def test_limit_does_not_discard_editor_lines_or_confirm_selection(app):
    values = editor(app)
    values['count'] = '50'
    for index in range(1, 50):
        values.update({f'source_{index}': 'inventory', f'catalog_id_{index}': values['catalog_id_0'],
                       f'quantity_{index}': '1'})
    key = open_picker(app, values)
    article = app.state.store.get_available_articles()[0]
    key = key_from(choose(app, key, article, apply=True))
    entry = app.state.order_drafts.get(key)
    assert entry['status'] == 400 and len(entry['rows']) == 50
    assert not entry['picker']['flow']['result']
    assert not app.state.store.get_journey()['orders']


def test_expiry_csrf_and_journey_change_protect_picker(app):
    key = open_picker(app)
    before = confirmed(app)
    assert form(app, {'editor_token': key}, url=PATH)[0] == 403
    assert confirmed(app) == before
    app.state.order_drafts.get(key)['session']['created'] -= 1801
    assert request(app, 'GET', f'/ordenes/borrador/{key}/articulos')[0] == 409
    assert submit_expired(app, key)[0] == 409
    key = open_picker(app)
    app.state.store.discard_journey()
    app.state.store.create_journey('Otra')
    assert submit(app, key, action='apply')[0] == 409


def submit_expired(app, key):
    return request(app, 'POST', PATH, {'editor_token': key, 'action': 'apply'}, form=True)


@pytest.mark.parametrize('viewport', VIEWPORTS)
def test_browser_multiple_selection_preserves_fields_and_layout(app, viewport):
    async def run():
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={'width': viewport[0], 'height': viewport[1]},
                                                java_script_enabled=False, is_mobile=viewport[0] <= 430,
                                                has_touch=viewport[0] <= 430)
            await context.route('**/*', lambda route: serve_asgi(app, route))
            page = await context.new_page()
            page.set_default_timeout(5000)
            try:
                await page.goto('http://127.0.0.1/ordenes/nueva')
                await page.get_by_label('Autor', exact=True).select_option(label='Ana')
                await page.get_by_label('Numeración', exact=True).fill('007')
                await page.get_by_role('button', name='Elegir artículos del inventario', exact=True).click()
                form = page.locator('.picker-page:visible')
                assert await page.locator('.picker-page:visible').count() == 1
                assert await form.locator('.picker-card').count() == (2 if viewport[0] < 375 else 3 if viewport[0] < 651 else 4 if viewport[0] < 1024 else 5)
                await assert_layout(page, viewport)
                label = await form.locator('.picker-choice').first.bounding_box()
                assert label['height'] >= 44
                before = confirmed(app)
                articles = [a for a in app.state.store.get_available_articles() if a['unit_price'] is not None][:2]
                for index, article in enumerate(articles):
                    await form.get_by_role('searchbox').fill(article['name'])
                    await form.get_by_role('button', name='Buscar', exact=True).click()
                    await form.get_by_role('checkbox', name='Seleccionar ' + article['name'], exact=True).check()
                    await form.get_by_label('Cantidad de ' + article['name'], exact=True).fill(str(index + 2))
                    if index == 0:
                        await form.get_by_role('searchbox').fill('SIN RESULTADOS')
                        await form.get_by_role('button', name='Buscar', exact=True).click()
                        assert await form.get_by_text('No hay artículos que coincidan con la búsqueda.').is_visible()
                        await assert_layout(page, viewport)
                await form.get_by_role('button', name='Agregar seleccionados', exact=True).click()
                assert confirmed(app) == before
                assert await page.locator('.order-line').count() == 2
                assert await page.get_by_label('Autor', exact=True).input_value() == app.state.store.get_journey()['authors'][0]['id']
                assert await page.get_by_label('Numeración', exact=True).input_value() == '007'
                assert await page.locator('[name=quantity_0]').input_value() == '2'
                assert await page.locator('[name=quantity_1]').input_value() == '3'
                await assert_layout(page, viewport)
                await page.get_by_role('button', name='Guardar orden', exact=True).click()
                assert await page.locator('#order-results').is_visible()
                saved = Store(app.state.store.global_file).get_journey()['orders']
                assert len(saved) == 1 and len(saved[0]['lines']) == 2
                assert [row['quantity'] for row in saved[0]['lines']] == [2, 3]
            finally:
                await browser.close()
    asyncio.run(run())


@pytest.mark.parametrize('field', ['search_q', 'category', 'subcategory'])
@pytest.mark.parametrize('value', ['x' * 201, 'x\x01'])
def test_filter_limits_preserve_selection(app, field, value):
    key = open_picker(app)
    article = app.state.store.get_available_articles()[0]
    key = key_from(choose(app, key, article, '2'))
    key = key_from(submit(app, key, changes={field: value}))
    entry = app.state.order_drafts.get(key)
    assert entry['status'] == 400
    assert entry['picker']['selected'] == {article['id']: '2'}


def test_search_is_accent_insensitive_and_html_is_escaped(app):
    key = open_picker(app)
    key = key_from(submit(app, key, changes={'search_q': 'cAfÉ'}))
    _, _, html = request(app, 'GET', f'/ordenes/borrador/{key}/articulos')
    assert '<legend>Cafe</legend>' in html
    key = key_from(submit(app, key, changes={'search_q': '<img src=x onerror=alert(1)>'}))
    _, _, html = request(app, 'GET', f'/ordenes/borrador/{key}/articulos')
    assert '<img src=x' not in html and '&lt;img src=x' in html


def test_picker_cannot_bypass_stale_order_check(app):
    order = create(app)
    key = open_picker(app, editor(app, order['id']), target=0)
    other = editor(app, order['id'])
    assert post(app, {**other, 'quantity_0': '9'})[0] == 303
    before = confirmed(app)
    article = next(a for a in app.state.store.get_available_articles() if a['id'] == other['catalog_id_0'])
    key = key_from(choose(app, key, article, '3', apply=True))
    response = post(app, form_values(app, key))
    assert request(app, 'GET', response[1]['location'])[0] == 409
    assert confirmed(app) == before


def test_same_article_selection_preserves_historical_price_when_catalog_changes(app):
    store = app.state.store
    order = create(app)
    line = order['lines'][0]
    article = next(a for a in store.get_available_articles() if a['id'] == line['catalog_id'])
    store.update_article(article['id'], {**article, 'unit_price': article['unit_price'] + 100})
    values = editor(app, order['id'])
    values.update(unit_price_0=str(line['unit_price']), line_id_0=line['line_id'])
    key = open_picker(app, values, target=0)
    key = key_from(choose(app, key, article, '2', apply=True))
    assert post(app, form_values(app, key))[0] == 303
    saved = Store(store.global_file).get_journey()['orders'][0]
    assert saved['lines'][0]['unit_price'] == line['unit_price']
    assert saved['lines'][0]['line_id'] == line['line_id']
