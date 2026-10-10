"""Comprobación operativa sin modificar jornadas ni requerir puertos expuestos."""
from copy import deepcopy
import json
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pytest

from order_manager.api import make_app
from order_manager import healthcheck
from test_review_fixes import request


def business_files(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*.json')
            if 'logs' not in p.relative_to(root).parts}


def health(app):
    status, _, body = request(app, 'GET', '/api/health')
    return status, json.loads(body)


def test_healthy_http_checks_io_and_leaves_business_unchanged(tmp_path):
    app = make_app(data_dir=tmp_path)
    store = app.state.store
    store.create_journey('Jornada')
    store.add_author('Ana')
    before = deepcopy(store._state())
    files = business_files(tmp_path)
    status, result = health(app)
    assert status == 200 and result['status'] == 'healthy'
    assert result['checks'] == {'initialized': True, 'revision': True, 'data_io': True}
    assert result['issues'] == []
    assert store._state() == before and business_files(tmp_path) == files
    assert not list(tmp_path.glob('.health-*'))
    store.runtime_log.close()


@pytest.mark.parametrize('component', ['inventory', 'global_stats', 'journey', 'operation'])
def test_essential_disk_damage_is_503_without_repair_or_reset(tmp_path, component):
    app = make_app(data_dir=tmp_path)
    store = app.state.store
    path = store.storage.component_path(component)
    path.write_text('secret-damaged-data')
    before = business_files(tmp_path)
    status, result = health(app)
    assert status == 503 and result['status'] == 'unavailable'
    assert 'essential_revision_unavailable' in result['issues']
    assert business_files(tmp_path) == before
    assert not store.storage.blocked and not (tmp_path / 'damaged').exists()
    assert 'secret-damaged-data' not in json.dumps(result)
    store.runtime_log.close()


@pytest.mark.parametrize('component', ['rollback', 'last_export'])
def test_optional_damage_is_degraded_without_touching_files(tmp_path, component):
    app = make_app(data_dir=tmp_path)
    store = app.state.store
    store.create_journey('Cerrada')
    store.close_journey()
    store.storage.component_path(component).write_text('dañado')
    before = business_files(tmp_path)
    status, result = health(app)
    assert status == 200 and result['status'] == 'degraded'
    assert f'optional_{component}_unavailable' in result['issues']
    assert business_files(tmp_path) == before
    store.runtime_log.close()


def test_manifest_schema_or_external_revision_is_not_ready(tmp_path):
    app = make_app(data_dir=tmp_path)
    store = app.state.store
    manifest = tmp_path / 'current.json'
    doc = json.loads(manifest.read_text())
    doc['schema'] = 999
    manifest.write_text(json.dumps(doc))
    assert health(app)[0] == 503
    doc['schema'] = 1
    doc['current']['id'] = 'a' * 32
    manifest.write_text(json.dumps(doc))
    assert health(app)[0] == 503
    store.runtime_log.close()


def test_blocked_startup_reports_unavailable(tmp_path):
    (tmp_path / 'current.json').write_text('dañado')
    app = make_app(data_dir=tmp_path)
    status, result = health(app)
    assert status == 503 and not result['checks']['initialized']
    assert 'storage_initialization_failed' in result['issues']
    app.state.store.runtime_log.close()


@pytest.mark.parametrize('failure', ['create', 'read', 'sync', 'cleanup'])
def test_io_failures_are_503_and_do_not_mutate_business(tmp_path, failure):
    app = make_app(data_dir=tmp_path)
    store = app.state.store
    before = business_files(tmp_path)
    if failure == 'create':
        target = 'order_manager.health.NamedTemporaryFile'
    elif failure == 'read':
        target = 'order_manager.health.Path.read_bytes'
    elif failure == 'sync':
        target = 'order_manager.health.os.fsync'
    else:
        target = 'order_manager.health.Path.unlink'
    with patch(target, side_effect=OSError('secret-io-error')):
        status, result = health(app)
    assert status == 503 and not result['checks']['data_io']
    assert 'data_io_failed' in result['issues']
    assert before == business_files(tmp_path)
    assert 'secret-io-error' not in json.dumps(result)
    if failure != 'cleanup':
        assert not list(tmp_path.glob('.health-*'))
    store.runtime_log.close()


def test_log_first_success_then_only_changes_and_failures(tmp_path):
    app = make_app(data_dir=tmp_path)
    assert health(app)[1]['status'] == 'healthy'
    assert health(app)[1]['status'] == 'healthy'
    with patch.object(app.state.health, '_writable', side_effect=OSError('fallo')):
        assert health(app)[0] == 503
        assert health(app)[0] == 503
    assert health(app)[0] == 200
    entries = [json.loads(l) for l in (tmp_path / 'logs' / 'application.log').read_text().splitlines()]
    states = [e['phase'] for e in entries if e['operation'] == 'healthcheck']
    assert states == ['healthy', 'unavailable', 'unavailable', 'healthy']
    app.state.store.runtime_log.close()


def test_log_failure_is_degraded_while_business_remains_available(tmp_path):
    app = make_app(data_dir=tmp_path)
    app.state.store.runtime_log.file.failed = True
    status, result = health(app)
    assert status == 200 and result['status'] == 'degraded'
    assert 'diagnostic_log_unavailable' in result['issues']
    app.state.store.runtime_log.close()


class FakeResponse:
    status = 200

    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, size):
        return self.body[:size]


@pytest.mark.parametrize('body', [b'not-json', b'[]', b'{"status":{}}',
                                 b'{"status":"healthy","checks":{}}', b'x' * 65537])
def test_script_rejects_incomplete_or_malformed_health(body):
    with patch('order_manager.healthcheck.build_opener') as opener:
        opener.return_value.open.return_value = FakeResponse(body)
        assert healthcheck.probe('http://127.0.0.1:8000/api/health', 3) == 'unavailable'


def test_script_probes_real_asgi_endpoint_without_network(tmp_path, capsys):
    app = make_app(data_dir=tmp_path)
    with patch('order_manager.healthcheck.build_opener') as opener:
        status, _, body = request(app, 'GET', '/api/health')
        assert status == 200
        opener.return_value.open.return_value = FakeResponse(body.encode())
        assert healthcheck.main([]) == 0
        assert opener.return_value.open.call_args.kwargs['timeout'] == 3
    assert json.loads(capsys.readouterr().out) == {'status': 'healthy', 'attempts': 1}
    app.state.store.runtime_log.close()


def test_script_retry_policy_and_persistent_http_failure(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    with patch('order_manager.healthcheck.build_opener') as opener, patch('order_manager.healthcheck.time.sleep') as sleep:
        opener.return_value.open.side_effect = URLError('secret-http-error')
        assert healthcheck.main([]) == 1
        assert opener.return_value.open.call_count == 3
        assert [c.args for c in sleep.call_args_list] == [(1.0,), (1.0,)]
    result = capsys.readouterr()
    assert json.loads(result.out) == {'status': 'unavailable', 'attempts': 3}
    assert 'secret-http-error' not in result.err
    entries = [json.loads(l) for l in (tmp_path / 'logs' / 'healthcheck.log').read_text().splitlines()]
    assert entries[-1]['operation'] == 'healthcheck_http_failed'
    assert not (tmp_path / 'logs' / 'application.log').exists()


def test_script_retries_then_accepts_degraded_status():
    with patch('order_manager.healthcheck.probe', side_effect=['unavailable', 'degraded']) as probe, patch('order_manager.healthcheck.time.sleep') as sleep:
        assert healthcheck.run('http://127.0.0.1:8000/api/health') == ('degraded', 2)
        assert probe.call_count == 2 and sleep.call_count == 1


@pytest.mark.parametrize('url', ['http://example.com/api/health', 'http://user:pass@127.0.0.1/api/health',
                               'http://127.0.0.1/api/health?secret=x', 'https://127.0.0.1/api/health'])
def test_script_rejects_remote_or_credential_urls(url):
    with pytest.raises(SystemExit) as error:
        healthcheck.main(['--url', url])
    assert error.value.code == 2
