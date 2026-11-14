"""Versión de origen en diagnóstico e historial, con compatibilidad de registros."""

import asyncio
from copy import deepcopy
import json
import logging
from unittest.mock import patch

import pytest
from playwright.async_api import async_playwright

from order_manager import __version__, persistence
from order_manager.api import make_app
from order_manager.runtime_logging import RuntimeLog
from order_manager.store import Store
from test_mobile import VIEWPORTS, assert_layout, serve_asgi
from test_review_fixes import request


def legacy_event(self, *args, **kwargs):
    original_event(self, *args, **kwargs)
    self._action_events[-1].pop('app_version', None)
    for event in self.journey['events']:
        event.pop('app_version', None)


original_event = Store._event


@pytest.mark.parametrize('filename', ['application.log', 'healthcheck.log'])
def test_diagnostic_appends_version_without_rewriting_previous_lines(tmp_path, filename):
    path = tmp_path / 'logs' / filename
    path.parent.mkdir()
    legacy = b'{"at":"2026-01-01T00:00:00+00:00","message":"Anterior"}\n'
    path.write_bytes(legacy)
    runtime = RuntimeLog(tmp_path, filename=filename)
    try:
        runtime.record(logging.INFO, 'Prueba.', 'version_test')
    finally:
        runtime.close()
    assert path.read_bytes().startswith(legacy)
    record = json.loads(path.read_text().splitlines()[-1])
    assert record['app_version'] == __version__
    assert record['operation'] == 'version_test'


def test_new_history_and_export_events_match_app_version_and_survive_rollback(tmp_path):
    app = make_app(data_dir=tmp_path)
    store = app.state.store
    store.create_journey('Turno')
    store.add_author('Ana')
    snapshot = deepcopy(store.get_journey())
    exported = json.loads(store.close_journey())
    history = store.get_events()
    assert all(event['app_version'] == app.version == __version__ for event in history)
    assert all(event['app_version'] == __version__ for event in exported['events'])
    assert exported['export_format'] == 'v0.2'
    assert exported['events'][-1]['action'] == 'journey_closed'
    store.runtime_log.close()
    restored = Store(store.global_file)
    assert restored.get_events() == history
    assert json.loads(restored.get_last_export()[1]) == exported
    info = restored.recovery_info()
    restored.recover_journey(info['close_id'], info['revision'], info['active_id'])
    assert restored.get_journey() == snapshot
    assert restored.get_events()[-1]['app_version'] == __version__
    restored.runtime_log.close()


def test_legacy_events_and_download_remain_unchanged_after_restart_and_new_actions(tmp_path):
    store = Store(tmp_path / 'global_stats.json')
    with patch.object(Store, '_event', legacy_event):
        store.create_journey('Anterior')
        store.add_author('Ana')
    before = deepcopy(store.get_journey()['events'])
    assert all('app_version' not in event for event in before)
    exported = store.close_journey()
    history_paths = list((tmp_path / 'logs' / 'actions').glob('*.json'))
    history_bytes = {path: path.read_bytes() for path in history_paths}
    store.runtime_log.close()
    app = make_app(data_dir=tmp_path)
    restored = app.state.store
    assert restored.get_last_export()[1] == exported
    assert restored.get_events()[0].get('app_version') is None
    status, _, html = request(app, 'GET', '/registros')
    assert status == 200 and 'No registrada' in html
    restored.create_journey('Nueva')
    assert restored.get_events()[-1]['app_version'] == __version__
    assert restored.get_last_export()[1] == exported
    assert all(path.read_bytes() == content for path, content in history_bytes.items())
    assert json.loads(exported)['events'][:-1] == before
    restored.runtime_log.close()


def test_pending_event_keeps_origin_version_when_retried_after_update(tmp_path):
    store = Store(tmp_path / 'global_stats.json')
    original_write = persistence.write_json

    def fail_history(path, value):
        if path.parent.name == 'actions':
            raise OSError('Historial no disponible')
        return original_write(path, value)

    with patch('order_manager.store.__version__', 'previous-build'):
        with patch.object(persistence, 'write_json', side_effect=fail_history):
            store.create_journey('Turno')
    assert store.get_events()[0]['app_version'] == 'previous-build'
    store.runtime_log.close()
    restored = Store(store.global_file)
    restored.add_author('Ana')
    assert [event['app_version'] for event in restored.get_events()] == ['previous-build', __version__]
    saved = [json.loads(path.read_text()) for path in (tmp_path / 'logs' / 'actions').glob('*.json')]
    assert sorted(event['app_version'] for event in saved) == sorted(['previous-build', __version__])
    restored.runtime_log.close()


@pytest.mark.parametrize('viewport', VIEWPORTS)
def test_records_show_versions_and_legacy_fallback_without_overflow(tmp_path, viewport):
    app = make_app(data_dir=tmp_path)
    with patch.object(Store, '_event', legacy_event):
        app.state.store.create_journey('Turno')
    app.state.store.add_author('Ana')

    async def run():
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    viewport={'width': viewport[0], 'height': viewport[1]}, java_script_enabled=False,
                )
                await context.route('**/*', lambda route: serve_asgi(app, route))
                page = await context.new_page()
                await page.goto('http://127.0.0.1/registros')
                versions = page.locator('td[data-label="Versión"]:visible')
                assert await versions.all_text_contents() == [__version__, 'No registrada']
                await assert_layout(page, viewport)
            finally:
                await browser.close()

    try:
        asyncio.run(run())
    finally:
        app.state.store.runtime_log.close()
