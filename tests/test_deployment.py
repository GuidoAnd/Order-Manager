"""Comprueba el contrato de arranque y el paquete sin daemon Docker."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / 'docker' / 'entrypoint.sh'


def launch(directory, *command, cwd=None):
    environment = os.environ.copy()
    environment['DATA_DIR'] = str(directory)
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    environment.pop('PYTHONPATH', None)
    return subprocess.run(
        ['sh', str(ENTRYPOINT), *command], cwd=cwd, env=environment,
        capture_output=True, text=True, timeout=30,
    )


@pytest.mark.parametrize('kind', ['missing', 'relative', 'file', 'empty'])
def test_invalid_data_directory_prevents_command_execution(tmp_path, kind):
    directory = {'missing': tmp_path / 'missing', 'relative': 'relative',
                 'file': tmp_path / 'file', 'empty': ''}[kind]
    (tmp_path / 'file').write_text('original')
    result = launch(directory, sys.executable, '-c', 'print("COMMAND_STARTED")', cwd=tmp_path)
    assert result.returncode == 64
    assert 'COMMAND_STARTED' not in result.stdout
    assert 'DATA_DIR' in result.stderr
    assert (tmp_path / 'file').read_text() == 'original'
    assert not (tmp_path / 'missing').exists()


def test_entrypoint_preserves_arguments_and_exit_status(tmp_path):
    directory = tmp_path / 'datos con espacios'
    directory.mkdir()
    result = launch(directory, sys.executable, '-c',
                    'import sys; print(sys.argv[1]); sys.exit(7)', 'valor con espacios')
    assert result.stdout.strip() == 'valor con espacios'
    assert result.returncode == 7


def test_missing_command_is_rejected(tmp_path):
    result = launch(tmp_path)
    assert result.returncode == 64
    assert 'Falta el comando' in result.stderr


def test_packaged_application_templates_and_persistence_across_restart(tmp_path):
    package = tmp_path / 'app'
    package.mkdir()
    shutil.copy(ROOT / 'api.py', package / 'api.py')
    for name in ('order_manager', 'static'):
        shutil.copytree(ROOT / name, package / name,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    directory = tmp_path / 'datos externos'
    directory.mkdir()
    script = '''
import asyncio
import json
from api import app
store = app.state.store
if store.get_journey() is None:
    store.create_journey('Persistente')
    store.add_author('Ana')
async def request(path):
    messages = []
    async def receive():
        return {'type': 'http.request', 'body': b'', 'more_body': False}
    async def send(message):
        messages.append(message)
    await app({'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
               'method': 'GET', 'scheme': 'http', 'path': path, 'raw_path': path.encode(),
               'query_string': b'', 'root_path': '', 'headers': [(b'host', b'localhost')],
               'client': ('127.0.0.1', 1), 'server': ('localhost', 80)}, receive, send)
    assert messages[0]['status'] == 200
    return b''.join(m.get('body', b'') for m in messages)
assert b'Persistente' in asyncio.run(request('/jornada'))
assert json.loads(asyncio.run(request('/api/health')))['status'] == 'healthy'
print(json.dumps(store.get_journey()))
store.runtime_log.close()
'''
    first = launch(directory, sys.executable, '-c', script, cwd=package)
    assert first.returncode == 0, first.stderr
    second = launch(directory, sys.executable, '-c', script, cwd=package)
    assert second.returncode == 0, second.stderr
    assert json.loads(first.stdout) == json.loads(second.stdout)
    assert (directory / 'current.json').is_file()
    assert not (package / 'data').exists()
    assert not list(package.rglob('__pycache__'))
