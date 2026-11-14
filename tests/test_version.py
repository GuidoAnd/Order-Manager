"""La versión de entrega coincide en API, OpenAPI, interfaz y Compose."""

import json
from pathlib import Path

from order_manager.api import make_app
from test_review_fixes import request


def test_release_version_is_consistent(tmp_path):
    app = make_app(data_dir=tmp_path / 'data')
    assert app.version == '0.3.2'
    status, _, body = request(app, 'GET', '/openapi.json')
    assert status == 200
    assert json.loads(body)['info']['version'] == '0.3.2'
    for path in ('/', '/jornada', '/ordenes', '/articulos', '/registros'):
        status, _, html = request(app, 'GET', path)
        assert status == 200
        assert '<a class="brand" href="/">Order Manager</a>' in html
        assert '<small>v0.3.2</small>' not in html
        assert '<footer>Order Manager · v0.3.2</footer>' in html
    compose = json.loads((Path(__file__).resolve().parents[1] / 'compose.json').read_text())
    assert compose['services']['order-manager']['image'] == 'order-manager:0.3.2'
