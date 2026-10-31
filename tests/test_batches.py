"""Tandas persistentes, correcciones y bloques independientes por autor."""

from copy import deepcopy
import json
import re

import pytest

from order_manager.api import make_app
from order_manager.order_batches import subtotal_blocks
from order_manager.state_validation import validate_state
from order_manager.store import DomainError, Store
from test_review_fixes import request
from test_security import form


@pytest.fixture
def setup(tmp_path):
    app = make_app(data_dir=tmp_path / 'data')
    store = app.state.store
    journey = store.create_journey('Turno')
    author = store.add_author('Ana')
    article = next(a for a in store.get_inventory()['articles'] if a['unit_price'] is not None)
    return app, journey, author, article


def open_batch(setup, series='10', author=None):
    app, journey, default, _ = setup
    author = author or default
    current = next(a for a in app.state.store.get_journey()['authors'] if a['id'] == author['id'])
    batches = current.get('batches', [])
    return app.state.store.open_batch(author['id'], series, journey['id'],
                                     batches[-1]['id'] if batches else '')


def values(app, author, article, order=None):
    url = f'/ordenes/{order["id"]}/editar' if order else '/ordenes/nueva'
    status, _, html = request(app, 'GET', url)
    assert status == 200
    assert 'name="series"' not in html
    token = re.search(r'name="editor_token" value="([^"]+)"', html).group(1)
    return dict(editor_token=token, order_id=order['id'] if order else '', author_id=author['id'],
                count='1', action='save', serial_number='001', source_0='inventory',
                catalog_id_0=article['id'], quantity_0='1')


def save(app, data):
    return request(app, 'POST', '/ui/orders/form', data, form=True, follow_editor=False)


def error_at(app, response, status, text):
    assert response[0] == 303
    code, _, html = request(app, 'GET', response[1]['location'])
    assert code == status and text in html
    return html


@pytest.mark.parametrize(('series', 'number'), [('10', 1), ('10', 80), ('20', 81), ('20', 160)])
def test_manual_number_inherits_assigned_series(setup, series, number):
    app, _, author, article = setup
    batch = open_batch(setup, series)
    data = values(app, author, article)
    result = save(app, {**data, 'serial_number': str(number), 'series': 'tampered'})
    assert result[0] == 303 and '/ordenes?' in result[1]['location']
    order = app.state.store.get_journey()['orders'][0]
    assert (order['series'], order['serial_number'], order['batch_id']) == (series, number, batch['id'])
    assert save(app, data)[1]['location'] == result[1]['location']
    assert len(app.state.store.get_journey()['orders']) == 1


@pytest.mark.parametrize(('series', 'number'), [('10', 81), ('20', 80), ('10', 0), ('20', 161),
                                               ('10', ''), ('10', '1.2')])
def test_range_validation_retains_editor(setup, series, number):
    app, _, author, article = setup
    open_batch(setup, series)
    data = values(app, author, article)
    before = deepcopy(app.state.store._state())
    html = error_at(app, save(app, {**data, 'serial_number': str(number)}), 400, 'Numeración:')
    assert f'name="serial_number"' in html
    assert app.state.store._state() == before


def test_no_assignment_and_stale_form_cannot_save(setup):
    app, journey, author, article = setup
    data = values(app, author, article)
    error_at(app, save(app, data), 409, 'asigne una serie y tanda')
    first = open_batch(setup)
    # Abrir una tanda posteriormente no legitima silenciosamente un formulario previo.
    error_at(app, save(app, data), 409, 'asigne una serie y tanda')
    fresh = values(app, author, article)
    app.state.store.close_batch(author['id'], first['id'], journey['id'])
    open_batch(setup)
    html = error_at(app, save(app, fresh), 409, 'tanda del autor cambió')
    assert 'value="001"' in html
    assert not app.state.store.get_journey()['orders']


def test_closed_batch_keeps_corrections_after_opening_another(setup):
    app, journey, author, article = setup
    first = open_batch(setup)
    assert save(app, values(app, author, article))[0] == 303
    order = app.state.store.get_journey()['orders'][0]
    data = values(app, author, article, order)
    app.state.store.close_batch(author['id'], first['id'], journey['id'])
    second = open_batch(setup, '20')
    assert save(app, {**data, 'quantity_0': '3', 'serial_number': '005'})[0] == 303
    corrected = app.state.store.get_journey()['orders'][0]
    assert corrected['batch_id'] == first['id'] and corrected['series'] == '10'
    assert corrected['lines'][0]['quantity'] == 3
    assert corrected['id'] == order['id'] and corrected['number'] == order['number']
    fresh = values(app, author, article, corrected)
    error_at(app, save(app, {**fresh, 'serial_number': '081'}), 400, 'Numeración:')
    new = values(app, author, article)
    assert save(app, {**new, 'serial_number': '081'})[0] == 303
    assert app.state.store.get_journey()['orders'][1]['batch_id'] == second['id']


def test_assignment_close_replay_wrong_journey_and_failure(setup, monkeypatch):
    app, journey, author, _ = setup
    store = app.state.store
    batch = open_batch(setup)
    before = deepcopy(store._state())
    with pytest.raises(DomainError):
        open_batch(setup, '20')
    assert store._state() == before
    with pytest.raises(DomainError):
        store.close_batch(author['id'], batch['id'], 'other-journey')
    original = store.storage.commit
    monkeypatch.setattr(store.storage, 'commit', lambda *args: (_ for _ in ()).throw(OSError('disk')))
    with pytest.raises(DomainError) as error:
        store.close_batch(author['id'], batch['id'], journey['id'])
    assert error.value.status == 503 and store._state() == before
    monkeypatch.setattr(store.storage, 'commit', original)
    store.close_batch(author['id'], batch['id'], journey['id'])
    with pytest.raises(DomainError):
        store.close_batch(author['id'], batch['id'], journey['id'])
    with pytest.raises(DomainError):
        store.open_batch(author['id'], '10', journey['id'], '')
    second = open_batch(setup)
    assert second['number'] == 2 and second['id'] != batch['id']


def test_blocks_skip_missing_numbers_separate_batches_and_include_gifts(setup):
    app, journey, author, article = setup
    store = app.state.store
    first = open_batch(setup, '20')
    for number in [91, 81, 83, 88, 99, 101, 102, 103, 104, 105, 106, 81]:
        store.save_order(author['id'], [{'catalog_id': article['id'], 'quantity': 1}],
                         serial_number=number, status='not_billed' if number == 88 else 'sale')
    store.close_batch(author['id'], first['id'], journey['id'])
    second = open_batch(setup, '20')
    store.save_order(author['id'], [{'catalog_id': article['id'], 'quantity': 1}], serial_number=81)
    data = store.get_journey()
    blocks = subtotal_blocks(data['authors'][0], data['orders'])
    assert [b['title'] for b in blocks] == ['Bloque 1 de la tanda 1', 'Bloque 2 de la tanda 1',
                                           'Bloque 1 de la tanda 2']
    assert [len(b['orders']) for b in blocks] == [10, 2, 1]
    assert [o['serial_number'] for o in blocks[0]['orders']][:5] == [81, 81, 83, 88, 91]
    assert blocks[2]['orders'][0]['batch_id'] == second['id']
    html = request(app, 'GET', '/jornada')[2]
    assert all(b['title'] in html for b in blocks)
    assert '0 · No facturada' in html
    assert store.get_summary()['orders'] == 12
    assert store.get_summary()['units'] == 12


def test_restart_export_rollback_and_persisted_validation(setup):
    app, journey, author, article = setup
    batch = open_batch(setup)
    store = app.state.store
    store.save_order(author['id'], [{'catalog_id': article['id'], 'quantity': 1}], serial_number=1)
    store.close_batch(author['id'], batch['id'], journey['id'])
    before = store.get_journey()
    assert Store(store.global_file).get_journey() == before
    invalid = deepcopy(store._state())
    invalid['journey']['data']['authors'][0]['batches'][0]['series'] = '20'
    with pytest.raises(ValueError):
        validate_state(invalid)
    payload = store.close_journey(journey['id'])
    exported = json.loads(payload)
    assert exported['authors'][0]['batches'][0]['id'] == batch['id']
    assert exported['orders'][0]['batch_id'] == batch['id']
    restarted = Store(store.global_file)
    validate_state(restarted._state())
    restored = restarted.recover_journey(restarted._export_close_id, restarted.storage.revision, '')
    assert restored['authors'] == before['authors'] and restored['orders'] == before['orders']


def test_legacy_orders_remain_editable_without_assigning_to_new_batch(setup):
    app, _, author, article = setup
    store = app.state.store
    old = store.save_order(author['id'], [{'catalog_id': article['id'], 'quantity': 1}])
    open_batch(setup, '20')
    data = values(app, author, article, old)
    assert save(app, {**data, 'serial_number': '005', 'quantity_0': '2'})[0] == 303
    corrected = store.get_journey()['orders'][0]
    assert 'batch_id' not in corrected and corrected['serial_number'] == 5
    assert 'Bloque 1 sin tanda asignada' in request(app, 'GET', '/jornada')[2]


def test_close_requires_confirmation_and_csrf(setup):
    app, journey, author, _ = setup
    batch = open_batch(setup)
    url = f'/tandas/{author["id"]}/{batch["id"]}/cerrar'
    before = deepcopy(app.state.store._state())
    assert request(app, 'GET', url)[0] == 200
    assert app.state.store._state() == before
    data = dict(action='close', author_id=author['id'], batch_id=batch['id'], journey_id=journey['id'])
    assert request(app, 'POST', '/ui/batches', data, form=True)[0] == 400
    assert form(app, {**data, 'confirm': 'yes'}, url='/ui/batches')[0] == 403
    assert app.state.store._state() == before
    response = request(app, 'POST', '/ui/batches', {**data, 'confirm': 'yes'}, form=True)
    assert response[0] == 303
    assert 'cerrada con éxito' in request(app, 'GET', response[1]['location'])[2]


def test_api_inherits_series_and_rejects_stale_batch(setup):
    app, journey, author, article = setup
    batch = open_batch(setup, '20')
    payload = dict(author_id=author['id'], series=None, serial_number=81, batch_id=batch['id'],
                   lines=[dict(catalog_id=article['id'], quantity=1)])
    code, _, body = request(app, 'POST', '/api/orders', payload)
    assert code == 201
    order = json.loads(body)
    assert order['series'] == '20' and order['batch_id'] == batch['id']
    app.state.store.close_batch(author['id'], batch['id'], journey['id'])
    code, _, _ = request(app, 'PUT', '/api/orders/' + order['id'], {**payload, 'serial_number': 83})
    assert code == 200
    open_batch(setup, '20')
    before = deepcopy(app.state.store._state())
    assert request(app, 'POST', '/api/orders', payload)[0] == 409
    assert app.state.store._state() == before


def test_concurrent_assignment_and_failed_open_do_not_duplicate_batches(setup, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    app, journey, author, _ = setup
    store = app.state.store
    before = deepcopy(store._state())
    original = store.storage.commit
    def failed(*args):
        raise OSError('disk')
    monkeypatch.setattr(store.storage, 'commit', failed)
    with pytest.raises(DomainError):
        open_batch(setup)
    assert store._state() == before
    monkeypatch.setattr(store.storage, 'commit', original)
    ready = Barrier(2)
    def assign():
        ready.wait()
        try:
            return store.open_batch(author['id'], '10', journey['id'])['number']
        except DomainError as error:
            return error.status
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: assign(), range(2))) == [1, 409]
    assert len(store.get_journey()['authors'][0]['batches']) == 1


def test_older_export_and_orders_are_preserved_when_assigning_batches(setup):
    app, _, author, article = setup
    store = app.state.store
    previous = store.save_order(author['id'], [{'catalog_id': article['id'], 'quantity': 1}],
                                series='10', serial_number=5)
    revision = store.storage.revision
    reopened = Store(store.global_file)
    assert reopened.storage.revision == revision
    assert reopened.get_journey()['orders'] == [previous]
    assert 'batches' not in reopened.get_journey()['authors'][0]
    payload = store.close_journey()
    assert 'batches' not in json.loads(payload)['authors'][0]
    current = store.create_journey('Nueva')
    next_author = store.add_author('Ana')
    store.open_batch(next_author['id'], '20', current['id'])
    assert store.get_last_export()[1] == payload
    assert Store(store.global_file).get_last_export()[1] == payload
    info = store.recovery_info()
    restored = store.recover_journey(info['close_id'], info['revision'], info['active_id'])
    assert restored['orders'] == [previous] and 'batches' not in restored['authors'][0]



def test_journey_close_closes_open_batches_and_rollback_restores_exact_state(setup):
    app, journey, author, article = setup
    store = app.state.store
    first = open_batch(setup)
    store.close_batch(author['id'], first['id'], journey['id'])
    open_batch(setup, '20')
    other = store.add_author('Beto')
    open_batch(setup, author=other)
    store.add_author('Sin asignación')
    store.save_order(author['id'], [{'catalog_id': article['id'], 'quantity': 1}], serial_number=81)
    before = store.get_journey()
    previous_close = before['authors'][0]['batches'][0]['closed_at']
    payload = store.close_journey(journey['id'])
    exported = json.loads(payload)
    assert exported['authors'][0]['batches'][0]['closed_at'] == previous_close
    for index in (0, 1):
        assert exported['authors'][index]['batches'][-1]['closed_at'] == exported['closed_at']
    assert 'batches' not in exported['authors'][2]
    assert exported['orders'] == before['orders']
    restarted = Store(store.global_file)
    assert restarted.get_journey() is None
    assert restarted.get_last_export()[1] == payload
    info = restarted.recovery_info()
    restored = restarted.recover_journey(info['close_id'], info['revision'], info['active_id'])
    assert restored == before
    assert Store(store.global_file).get_journey() == before
    restarted.save_order(author['id'], [{'catalog_id': article['id'], 'quantity': 1}], serial_number=83)
    reclosed = json.loads(restarted.close_journey(journey['id']))
    assert reclosed['authors'][0]['batches'][-1]['closed_at'] == reclosed['closed_at']
    assert reclosed['authors'][0]['batches'][0]['closed_at'] == previous_close


@pytest.mark.parametrize('failure', ['export', 'persistence'])
def test_failed_journey_close_keeps_batches_open_and_previous_export(setup, monkeypatch, failure):
    app, _, author, _ = setup
    store = app.state.store
    store.close_journey()
    current = store.create_journey('Nueva')
    author = store.add_author('Ana')
    store.open_batch(author['id'], '10', current['id'])
    before = deepcopy(store._state())
    revision = store.storage.revision
    def failed(*args):
        raise OSError('disk')
    if failure == 'export':
        monkeypatch.setattr('order_manager.store.build_export', failed)
    else:
        monkeypatch.setattr(store.storage, 'commit', failed)
    with pytest.raises(DomainError) as error:
        store.close_journey(current['id'])
    assert error.value.status == 503
    assert store._state() == before
    assert store.storage.revision == revision
    assert Store(store.global_file)._state() == before



def test_batch_panel_preserves_page_on_open_close_cancel_and_error(setup):
    app, journey, _, _ = setup
    store = app.state.store
    for number in range(6):
        author = store.add_author(f'Autor {number}')
    data = dict(action='open', author_id=author['id'], journey_id=journey['id'],
                series='20', previous_batch_id='', batch_page='2')
    response = request(app, 'POST', '/ui/batches', data, form=True)
    assert response[0] == 303 and 'batch_page=2' in response[1]['location']
    batch = store.get_journey()['authors'][-1]['batches'][0]
    response = request(app, 'POST', '/ui/batches', data, form=True)
    assert response[0] == 409
    assert 'Página 2 de 2' in response[2]
    url = f'/tandas/{author["id"]}/{batch["id"]}/cerrar?batch_page=2'
    status, _, html = request(app, 'GET', url)
    assert status == 200 and 'href="/jornada?batch_page=2#batch-results"' in html
    assert 'name="batch_page" value="2"' in html
    response = request(app, 'POST', '/ui/batches', {**data, 'action': 'close',
                       'batch_id': batch['id'], 'confirm': 'yes'}, form=True)
    assert response[0] == 303 and 'batch_page=2' in response[1]['location']
    assert request(app, 'POST', '/ui/batches', {**data, 'batch_page': 'invalid'}, form=True)[0] == 409


def test_block_totals_recalculate_after_corrections_deletion_and_author_transfer(setup):
    app, journey, author, article = setup
    store = app.state.store
    first = open_batch(setup, '20')
    lines = [{'catalog_id': article['id'], 'quantity': 1}]
    for number in [81, 83, 88, 91, 92, 94, 96, 99, 105, 110, 111]:
        store.save_order(author['id'], lines, serial_number=number)
    store.close_batch(author['id'], first['id'], journey['id'])
    open_batch(setup, '20')
    store.save_order(author['id'], lines, serial_number=81)
    previous = store.get_journey()['orders']
    gift = previous[2]
    store.save_order(author['id'], lines, gift['id'], status='not_billed', serial_number=88)
    store.delete_order(previous[0]['id'])
    destination = store.add_author('Beto')
    assigned = open_batch(setup, '10', destination)
    moved = store.save_order(destination['id'], lines, previous[1]['id'], serial_number=5)
    assert moved['batch_id'] == assigned['id'] and moved['series'] == '10'
    journey = store.get_journey()
    subtotals = []
    for current_author in journey['authors']:
        orders = [o for o in journey['orders'] if o['author_id'] == current_author['id']]
        blocks = subtotal_blocks(current_author, orders)
        assert sorted(o['id'] for b in blocks for o in b['orders']) == sorted(o['id'] for o in orders)
        for block in blocks:
            assert 1 <= len(block['orders']) <= 10
            subtotal = sum(o['total'] for o in block['orders'] if o['status'] == 'sale')
            subtotals.append(subtotal)
            assert len({o.get('batch_id') for o in block['orders']}) == 1
    assert sum(subtotals) == store.get_summary()['revenue']
    assert sum(subtotals) == 10 * article['unit_price']
