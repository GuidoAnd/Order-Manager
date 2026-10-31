"""Confirmaciones de operaciones, aislamiento y avisos accesibles sin JavaScript."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from html import unescape
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.async_api import async_playwright

from order_manager.api import make_app
from order_manager.notices import MESSAGES, OperationNotices
from order_manager.store import DomainError
from test_mobile import VIEWPORTS, assert_layout, serve_asgi
from test_order_navigation import app, confirmed, create, editor, post
from test_review_fixes import request
from test_security import form


def message_at(app, response, expected):
    assert response[0] == 303
    location = response[1]['location']
    assert urlsplit(location).fragment == 'operation-notice'
    status, headers, html = request(app, 'GET', location)
    assert status == 200 and headers['cache-control'] == 'no-store'
    assert 'id="operation-notice" role="status"' in html
    assert expected in unescape(html)
    assert 'Ocultar aviso' not in html
    before = confirmed(app)
    assert request(app, 'GET', location)[0] == 200
    assert confirmed(app) == before
    return location, html


def test_order_create_edit_delete_confirm_only_after_success(app):
    data = editor(app)
    response = post(app, data)
    location, _ = message_at(app, response, 'La orden 001 de Ana ha sido exitosamente guardada!')
    before = confirmed(app)
    assert post(app, data)[1]['location'] == location
    assert confirmed(app) == before
    order = app.state.store.get_journey()['orders'][0]
    response = post(app, {**editor(app, order['id']), 'quantity_0': '3'})
    message_at(app, response, 'Orden 001 ha sido modificada con éxito!')
    response = request(app, 'POST', '/ui/orders/delete', {'order_id': order['id']}, form=True)
    message_at(app, response, 'La orden 001 de Ana ha sido eliminada!')
    assert not app.state.store.get_journey()['orders']


def test_notices_preserve_order_filters(app):
    values = editor(app)
    values.update(q='Ana & <otra>', page='3', article='seed-061')
    response = post(app, values)
    target, html = message_at(app, response, 'La orden 001 de Ana ha sido exitosamente guardada!')
    query = parse_qs(urlsplit(target).query)
    assert query['q'] == ['Ana & <otra>'] and query['page'] == ['3'] and query['article'] == ['seed-061']


def test_article_create_edit_delete_notice_and_filters(app):
    values = dict(name='Prueba de aviso', category='Otros', subcategory='Otros', unit_price='10',
                  q='aviso', page='2', sold_page='3')
    response = request(app, 'POST', '/ui/articles', values, form=True)
    location, _ = message_at(app, response, MESSAGES['article_created'])
    query = parse_qs(urlsplit(location).query)
    assert query['page'] == ['2'] and query['sold_page'] == ['3'] and query['q'] == ['aviso']
    article = next(a for a in app.state.store.get_inventory()['articles'] if a['name'] == values['name'])
    response = request(app, 'POST', '/ui/articles', {**values, 'article_id': article['id'], 'unit_price': '20'}, form=True)
    message_at(app, response, 'Prueba de aviso ha sido modificado con éxito!')
    response = request(app, 'POST', '/ui/articles', {'action': 'delete', 'article_id': article['id']}, form=True)
    message_at(app, response, MESSAGES['article_deleted'])


def test_journey_and_author_operations_confirmations(app):
    store = app.state.store
    journey_id = store.get_journey()['id']
    response = request(app, 'POST', '/ui/journey', {'action': 'rename', 'journey_id': journey_id, 'title': 'Nuevo nombre'}, form=True)
    message_at(app, response, MESSAGES['journey_updated'])
    response = request(app, 'POST', '/ui/journey', {'action': 'add_author', 'name': 'Bea'}, form=True)
    message_at(app, response, 'Bea ha sido agregado a la jornada Nuevo nombre.')
    author = next(a for a in store.get_journey()['authors'] if a['name'] == 'Bea')
    response = request(app, 'POST', '/ui/journey', {'action': 'rename_author', 'author_id': author['id'], 'name': 'Beto'}, form=True)
    message_at(app, response, MESSAGES['author_updated'])
    response = request(app, 'POST', '/ui/journey', {'action': 'delete_author', 'author_id': author['id']}, form=True)
    message_at(app, response, MESSAGES['author_deleted'])
    response = request(app, 'POST', '/ui/journey', {'action': 'discard', 'journey_id': journey_id, 'confirm': 'yes'}, form=True)
    message_at(app, response, MESSAGES['journey_discarded'])
    response = request(app, 'POST', '/ui/journey', {'action': 'create', 'title': 'Nueva jornada'}, form=True)
    message_at(app, response, MESSAGES['journey_created'])


def test_close_recover_notices_and_direct_download(app):
    store = app.state.store
    create(app)
    journey_id = store.get_journey()['id']
    response = request(app, 'POST', '/ui/journey', {'action': 'close', 'journey_id': journey_id, 'confirm': 'yes'}, form=True)
    target, html = message_at(app, response, MESSAGES['journey_closed'])
    assert 'download-help' not in html
    assert 'method="get" action="/api/exports/last"' in html
    info = store.recovery_info()
    response = request(app, 'POST', '/ui/journey', {
        'action': 'recover', 'confirm': 'yes', 'close_id': info['close_id'],
        'revision': info['revision'], 'active_id': '',
    }, form=True)
    message_at(app, response, 'Jornada Turno ha sido recuperada exitosamente!')
    # Un aviso de cierre anterior no debe acompañar un error de exportación.
    status, _, html = request(app, 'GET', target)
    assert status == 404 and 'id="operation-notice"' not in html


@pytest.mark.parametrize('kind', ['order', 'article', 'journey', 'csrf', 'storage', 'conflict'])
def test_failed_operation_never_issues_success_notice(app, monkeypatch, kind):
    if kind == 'conflict':
        order = create(app)
        data = editor(app, order['id'])
        post(app, {**editor(app, order['id']), 'quantity_0': '9'})
    else:
        data = editor(app)
    before = len(app.state.operation_notices.entries)
    if kind == 'order':
        response = post(app, {**data, 'quantity_0': '0'})
        response = request(app, 'GET', response[1]['location'])
        expected = 400
    elif kind == 'article':
        response = request(app, 'POST', '/ui/articles', {'name': '', 'category': 'Otros'}, form=True)
        expected = 400
    elif kind == 'journey':
        response = request(app, 'POST', '/ui/journey', {'action': 'discard', 'confirm': 'no'}, form=True)
        expected = 400
    elif kind == 'csrf':
        response = form(app, {'action': 'add_author', 'name': 'Sin CSRF'}, url='/ui/journey')
        expected = 403
    else:
        if kind == 'storage':
            def fail(*args, **kwargs):
                raise OSError('fallo simulado')
            monkeypatch.setattr(app.state.store.storage, 'commit', fail)
        response = post(app, data)
        response = request(app, 'GET', response[1]['location'])
        expected = 503 if kind == 'storage' else 409
    assert response[0] == expected
    body = response[2].decode() if isinstance(response[2], bytes) else response[2]
    assert 'id="operation-notice"' not in body
    assert len(app.state.operation_notices.entries) == before


def test_notice_is_scoped_to_token_destination_and_instance(app, tmp_path):
    target = post(app, editor(app))[1]['location']
    token = parse_qs(urlsplit(target).query)['notice'][0]
    before = confirmed(app)
    for path in ['/ordenes', '/ordenes?notice=order_created', '/jornada?notice=' + token]:
        assert 'id="operation-notice"' not in request(app, 'GET', path)[2]
    other = make_app(data_dir=tmp_path / 'other')
    assert 'id="operation-notice"' not in request(other, 'GET', target)[2]
    for _ in range(2):
        assert 'La orden 001 de Ana ha sido exitosamente guardada!' in request(app, 'GET', target)[2]
    assert confirmed(app) == before
    app.state.operation_notices.entries[token]['created'] -= 301
    assert 'id="operation-notice"' not in request(app, 'GET', target)[2]


def test_notice_capacity_and_unknown_code():
    notices = OperationNotices()
    notices.max_entries = 2
    first = notices.url('/jornada', 'journey_created')
    notices.url('/jornada', 'journey_updated')
    notices.url('/jornada', 'journey_discarded')
    assert len(notices.entries) == 2
    assert notices.get(parse_qs(urlsplit(first).query)['notice'][0], '/jornada') is None
    with pytest.raises(ValueError):
        notices.url('/jornada', '<script>')


@pytest.mark.parametrize('viewport', VIEWPORTS)
def test_browser_notice_hides_after_eight_seconds_and_downloads_direct(app, viewport):
    target = post(app, editor(app))[1]['location']
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
                await page.goto('http://127.0.0.1' + target)
                notice = page.locator('#operation-notice')
                assert await notice.is_visible()
                assert await notice.get_attribute('role') == 'status'
                assert await notice.evaluate('node => getComputedStyle(node).position') == 'static'
                assert 'La orden 001 de Ana ha sido exitosamente guardada!' in await notice.inner_text()
                await assert_layout(page, viewport)
                box = await notice.bounding_box()
                assert box['y'] >= -1 and box['y'] < viewport[1]
                assert await notice.locator('a, button').count() == 0
                assert await notice.evaluate('node => getComputedStyle(node).animationDelay') == '8s'
                assert await notice.evaluate('node => getComputedStyle(node).animationDuration') == '0s'
                before = confirmed(app)
                await notice.wait_for(state='hidden', timeout=10000)
                assert await notice.evaluate('node => node.getBoundingClientRect().height') == 0
                assert await notice.evaluate('node => getComputedStyle(node).marginBottom') == '0px'
                assert confirmed(app) == before
                await assert_layout(page, viewport)
                assert await page.locator('#order-results').is_visible()
                store = app.state.store
                journey_id = store.get_journey()['id']
                store.close_journey(journey_id)
                await page.goto(f'http://127.0.0.1/exportaciones?journey_id={journey_id}')
                assert await page.locator('.download-help').count() == 0
                button = page.get_by_role('button', name='Descargar', exact=True)
                await assert_layout(page, viewport)
                async with page.expect_download() as pending:
                    await button.click()
                assert (await pending.value).suggested_filename == f'jornada-{journey_id}.zip'
                assert await page.locator('.download-help').count() == 0
            finally:
                await browser.close()
    asyncio.run(run())


def test_notice_does_not_leak_between_concurrent_requests(app):
    target = post(app, editor(app))[1]['location']
    paths = [target, '/ordenes'] * 4
    with ThreadPoolExecutor(max_workers=4) as pool:
        pages = list(pool.map(lambda path: request(app, 'GET', path)[2], paths))
    assert [('id="operation-notice"' in page) for page in pages] == [True, False] * 4


def test_failure_rendering_destination_hides_old_notice(app, monkeypatch):
    target = post(app, editor(app))[1]['location']
    def unavailable():
        raise DomainError('Almacenamiento no disponible.', 503)
    monkeypatch.setattr(app.state.store, 'get_journey', unavailable)
    status, _, html = request(app, 'GET', target)
    assert status == 503 and 'role="alert"' in html
    assert 'id="operation-notice"' not in html


def test_order_notices_use_confirmed_number_and_current_author(app):
    store = app.state.store
    author = store.get_journey()['authors'][0]
    store.rename_author(author['id'], 'Bea')
    data = editor(app)
    data['serial_number'] = '005'
    response = post(app, data)
    message_at(app, response, 'La orden 005 de Bea ha sido exitosamente guardada!')
    order = store.get_journey()['orders'][0]
    other = store.add_author('Caro')
    store.open_batch(other['id'], '20', store.get_journey()['id'])
    response = post(app, {**editor(app, order['id']), 'author_id': other['id'],
                          'series': '20', 'serial_number': '081'})
    message_at(app, response, 'Orden 081 ha sido modificada con éxito!')
    store.rename_author(other['id'], 'Dani')
    response = request(app, 'POST', '/ui/orders/delete', {'order_id': order['id']}, form=True)
    message_at(app, response, 'La orden 081 de Dani ha sido eliminada!')


def test_author_notice_uses_normalized_names_and_escapes_html(app):
    store = app.state.store
    store.rename_journey('Feria <b> & Centro')
    response = request(app, 'POST', '/ui/journey', {
        'action': 'add_author', 'name': '  <script>Bea</script> & Ana  ',
    }, form=True)
    _, html = message_at(app, response,
        '<script>Bea</script> & Ana ha sido agregado a la jornada Feria <b> & Centro.')
    assert '<script>Bea</script>' not in html and '&lt;script&gt;Bea&lt;/script&gt;' in html
    assert 'Feria <b>' not in html and 'Feria &lt;b&gt;' in html


def test_recovery_notice_names_restored_journey_instead_of_discarded_one(app):
    store = app.state.store
    store.rename_journey('Ventas del centro')
    store.close_journey()
    store.create_journey('Otra jornada abierta')
    info = store.recovery_info()
    response = request(app, 'POST', '/ui/journey', {
        'action': 'recover', 'confirm': 'yes', 'close_id': info['close_id'],
        'revision': info['revision'], 'active_id': info['active_id'],
    }, form=True)
    message_at(app, response, 'Jornada Ventas del centro ha sido recuperada exitosamente!')


def test_legacy_order_notice_uses_its_existing_counter():
    from order_manager.notices import order_details
    details = order_details({'number': 7, 'author_id': 'ana'}, {'authors': [{'id': 'ana', 'name': 'Ana'}]})
    assert details == {'number': '7', 'author': 'Ana'}


def test_article_notice_uses_confirmed_new_name_after_rename(app):
    store = app.state.store
    article = next(a for a in store.get_available_articles() if a['name'] == 'Cafe')
    response = request(app, 'POST', '/ui/articles', {
        'article_id': article['id'], 'name': '  Café especial  ', 'category': article['category'],
        'subcategory': article['subcategory'], 'unit_price': '3000',
    }, form=True)
    message_at(app, response, 'Café especial ha sido modificado con éxito!')
