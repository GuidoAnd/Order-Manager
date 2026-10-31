"""Navegación GET, conflictos y reenvíos del editor sin perder órdenes confirmadas."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import re
from threading import Barrier

import pytest

from order_manager.api import make_app
from order_manager.store import Store
from test_review_fixes import request


@pytest.fixture
def app(tmp_path):
    app = make_app(data_dir=tmp_path / 'data')
    app.state.store.create_journey('Turno')
    author = app.state.store.add_author('Ana')
    app.state.store.open_batch(author['id'], '10', app.state.store.get_journey()['id'])
    return app


def editor(app, order_id=''):
    path = f'/ordenes/{order_id}/editar' if order_id else '/ordenes/nueva'
    status, _, html = request(app, 'GET', path)
    assert status == 200
    key = re.search(r'name="editor_token" value="([^"]+)"', html).group(1)
    store = app.state.store
    article = next(a for a in store.get_inventory()['articles'] if a['unit_price'] is not None)
    return dict(editor_token=key, order_id=order_id, action='save', count='1',
                author_id=store.get_journey()['authors'][0]['id'], series='10', serial_number='1',
                source_0='inventory', catalog_id_0=article['id'], quantity_0='1')


def post(app, values):
    return request(app, 'POST', '/ui/orders/form', values, form=True, follow_editor=False)


def create(app):
    assert post(app, editor(app))[0] == 303
    return app.state.store.get_journey()['orders'][-1]


def confirmed(app):
    store = app.state.store
    return deepcopy(store._state()), store.storage.revision


@pytest.mark.parametrize('action', ['add', 'remove_0', 'remove_-1', 'remove_100', 'unknown', 'save'])
def test_draft_actions_and_errors_redirect_to_read_only_get(app, action):
    data = editor(app)
    data.update(action=action, quantity_0='0', q='Ana', page='2')
    before = confirmed(app)
    status, headers, _ = post(app, data)
    assert status == 303
    assert headers['location'].startswith('/ordenes/borrador/')
    assert 'Ana' not in headers['location'] and data['author_id'] not in headers['location']
    expected = 200 if action in {'add', 'remove_0'} else 400
    for _ in range(2):
        code, headers_get, html = request(app, 'GET', headers['location'])
        assert code == expected and headers_get['cache-control'] == 'no-store'
        assert 'name="q" value="Ana"' in html and 'name="page" value="2"' in html
        assert confirmed(app) == before
    assert Store(app.state.store.global_file).get_journey()['orders'] == []


def test_all_snapshots_of_saved_editor_are_consumed(app):
    data = editor(app)
    status, headers, _ = post(app, {**data, 'action': 'add'})
    assert status == 303
    _, _, html = request(app, 'GET', headers['location'])
    next_key = re.search(r'name="editor_token" value="([^"]+)"', html).group(1)
    first = post(app, data)
    before = confirmed(app)
    assert first[0] == 303 and '#operation-notice' in first[1]['location']
    for key in [data['editor_token'], next_key]:
        again = post(app, {**data, 'editor_token': key})
        assert again[:2] == first[:2]
        assert confirmed(app) == before
        get = request(app, 'GET', '/ordenes/borrador/' + key)
        assert get[0] == 303 and get[1]['location'] == first[1]['location']
    assert len(Store(app.state.store.global_file).get_journey()['orders']) == 1


def test_independent_identical_orders_are_still_allowed(app):
    a, b = editor(app), editor(app)
    assert post(app, a)[0] == post(app, b)[0] == 303
    assert len(app.state.store.get_journey()['orders']) == 2


@pytest.mark.parametrize('delete', [False, True])
def test_stale_editor_rejected_preserves_input_and_confirmed_state(app, delete):
    order = create(app)
    stale = editor(app, order['id'])
    current = editor(app, order['id'])
    if delete:
        app.state.store.delete_order(order['id'])
    else:
        assert post(app, {**current, 'quantity_0': '9'})[0] == 303
    before = confirmed(app)
    response = post(app, {**stale, 'quantity_0': '7'})
    assert response[0] == 303
    status, _, html = request(app, 'GET', response[1]['location'])
    assert status == 409 and 'value="7"' in html and 'La orden cambió' in html
    assert confirmed(app) == before
    assert Store(app.state.store.global_file).get_journey() == app.state.store.get_journey()


def test_journey_change_rejects_old_draft_and_preserves_fields(app):
    data = editor(app)
    app.state.store.discard_journey()
    app.state.store.create_journey('Otro turno')
    before = confirmed(app)
    response = post(app, {**data, 'quantity_0': '7'})
    status, _, html = request(app, 'GET', response[1]['location'])
    assert status == 409 and 'La jornada cambió' in html and 'value="7"' in html
    assert confirmed(app) == before


@pytest.mark.parametrize('reason', ['expired', 'evicted', 'restart', 'missing', 'foreign_order'])
def test_unavailable_or_tampered_editor_never_mutates(app, reason):
    data = editor(app)
    if reason == 'expired':
        app.state.order_drafts.entries[data['editor_token']]['session']['created'] -= 1801
    elif reason == 'evicted':
        app.state.order_drafts.max_entries = 1
        editor(app)
    elif reason == 'restart':
        app = make_app(data_dir=app.state.store.data_dir)
    elif reason == 'missing':
        data['editor_token'] = ''
    else:
        data['order_id'] = 'another-order'
    before = confirmed(app)
    assert post(app, data)[0] == 409
    assert confirmed(app) == before


def test_storage_failure_does_not_consume_submission(app, monkeypatch):
    data = editor(app)
    before = confirmed(app)
    with monkeypatch.context() as patch:
        def fail(*args, **kwargs):
            raise OSError('test failure')
        patch.setattr(app.state.store.storage, 'commit', fail)
        response = post(app, data)
        assert response[0] == 303
        assert request(app, 'GET', response[1]['location'])[0] == 503
        assert confirmed(app) == before
    assert post(app, data)[0] == 303
    assert len(Store(app.state.store.global_file).get_journey()['orders']) == 1


@pytest.mark.parametrize('same_editor', [False, True])
def test_concurrent_submissions_are_atomic(app, same_editor):
    if same_editor:
        a = editor(app)
        b = deepcopy(a)
    else:
        order = create(app)
        a, b = editor(app, order['id']), editor(app, order['id'])
        a['quantity_0'], b['quantity_0'] = '4', '8'
    gate = Barrier(2)
    def submit(data):
        gate.wait(timeout=5)
        result = post(app, data)
        return (request(app, 'GET', result[1]['location'])[0]
                if '/borrador/' in result[1]['location'] else result[0])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, [a, b]))
    assert sorted(results) == ([303, 303] if same_editor else [303, 409])
    assert len(Store(app.state.store.global_file).get_journey()['orders']) == 1


def test_memory_limit_rejects_excess_without_touching_orders(app):
    data = editor(app)
    app.state.order_drafts.max_bytes = 10
    before = confirmed(app)
    assert post(app, {**data, 'action': 'add'})[0] == 413
    assert confirmed(app) == before


@pytest.mark.parametrize('viewport', [(320, 568), (375, 667), (430, 932), (768, 1024), (1366, 768)])
def test_browser_back_to_draft_never_replays_save(app, viewport):
    import asyncio
    from playwright.async_api import async_playwright
    from test_mobile import assert_layout, serve_asgi, choose_order_article

    order = create(app)
    async def run():
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={'width': viewport[0], 'height': viewport[1]},
                java_script_enabled=False, is_mobile=viewport[0] <= 430,
                has_touch=viewport[0] <= 430,
            )
            calls = []
            async def respond(route):
                calls.append((route.request.method, route.request.url))
                await serve_asgi(app, route)
            await context.route('**/*', respond)
            page = await context.new_page()
            page.set_default_timeout(5000)
            await page.goto(f"http://127.0.0.1/ordenes/{order['id']}/editar")
            await page.locator('[name=quantity_0]').fill('2')
            await page.get_by_role('button', name='Agregar artículo', exact=True).click()
            catalog = await page.locator('[name=catalog_id_0]').input_value()
            name = next(a['name'] for a in app.state.store.get_order_inventory(order['id'])['articles'] if a['id'] == catalog)
            await choose_order_article(page, 1, name)
            await page.locator('[name=quantity_1]').fill('1')
            key = await page.locator('[name=editor_token]').input_value()
            # El adaptador sigue 303 internamente. Abrir explícitamente su GET
            # permite probar historial GET sin fingir una redirección de red.
            await page.goto('http://127.0.0.1/ordenes/borrador/' + key)
            assert await page.locator('[name=quantity_0]').input_value() == '2'
            await assert_layout(page, viewport)
            await page.get_by_role('button', name='Guardar orden', exact=True).click()
            await page.locator('#order-results').wait_for()
            before = confirmed(app)
            posts = sum(method == 'POST' for method, _ in calls)
            await page.go_back(wait_until='domcontentloaded')
            await page.locator('#order-results').wait_for()
            assert sum(method == 'POST' for method, _ in calls) == posts
            assert confirmed(app) == before
            persisted = Store(app.state.store.global_file).get_journey()['orders']
            assert len(persisted) == 1 and len(persisted[0]['lines']) == 2
            assert persisted[0]['id'] == order['id']
            await assert_layout(page, viewport)
            await browser.close()
    asyncio.run(run())
