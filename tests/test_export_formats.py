"""Formatos de descarga, agregación de ventas y consistencia del cierre."""

from copy import deepcopy
import csv
from io import BytesIO, StringIO
import json
from zipfile import ZipFile

import pytest

from order_manager.api import make_app
from order_manager.export_formats import download_file, sold_articles
from test_review_fixes import request


def csv_rows(payload):
    assert payload.startswith(b"\xef\xbb\xbf")
    return list(csv.reader(StringIO(payload.decode("utf-8-sig")), delimiter=";"))


def prepare(app):
    store = app.state.store
    journey = store.create_journey("Turno CSV")
    ana = store.add_author("Ana")
    bea = store.add_author("Bea")
    coffee = next(item for item in store.get_available_articles() if item["name"] == "Cafe")
    store.save_order(ana["id"], [{"catalog_id": coffee["id"], "quantity": 3}])
    store.update_article(coffee["id"], {
        "name": "Cafe", "category": "Cafetería", "subcategory": "Infusiones",
        "unit_price": 3000,
    })
    store.save_order(bea["id"], [{"catalog_id": coffee["id"], "quantity": 2}])
    store.save_order(bea["id"], [{
        "name": "Agua nueva", "category": "Otros", "subcategory": "Otros",
        "unit_price": 700, "quantity": 4,
    }])
    store.save_order(ana["id"], [{
        "name": "Solo regalo", "category": "Otros", "subcategory": "Otros",
        "quantity": 9,
    }], status="not_billed")
    return journey["id"]


def test_csv_aggregates_authors_with_original_prices(tmp_path):
    app = make_app(tmp_path / "globals.json")
    journey_id = prepare(app)
    store = app.state.store
    payload = store.close_journey()
    export = json.loads(payload)
    original = deepcopy(export)
    items = sold_articles(export)
    assert items == [
        {"category": "Cafetería", "subcategory": "Infusiones", "name": "Cafe",
         "units": 5, "revenue": 14400},
        {"category": "Otros", "subcategory": "Otros", "name": "Agua nueva",
         "units": 4, "revenue": 2800},
    ]
    detail = csv_rows(download_file(journey_id, payload, "csv_detail")[2])
    assert detail == [
        ["Categoría", "Subcategoría", "Artículo", "Unidades", "Importe"],
        ["Cafetería", "Infusiones", "Cafe", "5", "14400"],
        ["Otros", "Otros", "Agua nueva", "4", "2800"],
    ]
    assert csv_rows(download_file(journey_id, payload, "csv_summary")[2]) == [
        ["Cafetería", "Cafe [Infusiones]"], ["Unidades", "5"],
        ["Otros", "Agua nueva [Otros]"], ["Unidades", "4"],
    ]
    assert sum(item["units"] for item in items) == export["statistics"]["units"]
    assert sum(item["revenue"] for item in items) == export["statistics"]["revenue"]
    assert export == original


@pytest.mark.parametrize("has_gift", [False, True])
def test_csv_without_sales_contains_no_inventory(tmp_path, has_gift):
    app = make_app(tmp_path / "globals.json")
    store = app.state.store
    journey = store.create_journey("Sin ventas")
    if has_gift:
        author = store.add_author("Ana")
        coffee = next(item for item in store.get_available_articles() if item["name"] == "Cafe")
        store.save_order(author["id"], [{"catalog_id": coffee["id"], "quantity": 2}],
                         status="not_billed")
    payload = store.close_journey()
    assert csv_rows(download_file(journey["id"], payload, "csv_detail")[2]) == [
        ["Categoría", "Subcategoría", "Artículo", "Unidades", "Importe"],
    ]
    assert csv_rows(download_file(journey["id"], payload, "csv_summary")[2]) == [
        ["Categoría / artículo"],
    ]


def test_special_names_distinct_identity_and_rectangular_summary():
    names = ["Agua; fría", 'Agua "especial"\nsegunda línea', "Agua / fría", "=SUM(A1)"]
    lines = [
        {"name": name, "category": "Bebidas", "subcategory": "Aguas",
         "quantity": index + 1, "subtotal": 0}
        for index, name in enumerate(names)
    ]
    lines.append({**lines[0], "subcategory": "Otra", "quantity": 2})
    lines.append({**lines[0], "category": "Otros", "quantity": 3})
    payload = json.dumps({"orders": [{"lines": lines}]}).encode()
    detail = csv_rows(download_file("id", payload, "csv_detail")[2])
    assert len(detail) == 7
    assert sum(int(row[3]) for row in detail[1:]) == 15
    assert sum(row[2] == "Agua; fría" for row in detail[1:]) == 3
    assert any(row[2] == "'=SUM(A1)" for row in detail[1:])
    assert any(row[2] == names[1] for row in detail[1:])
    summary = csv_rows(download_file("id", payload, "csv_summary")[2])
    assert len({len(row) for row in summary}) == 1
    assert any("Agua; fría [Otra]" in row for row in summary)


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "  ="])
def test_csv_names_are_text_not_formulas(prefix):
    payload = json.dumps({"orders": [{"lines": [{
        "category": prefix + "grupo", "subcategory": prefix + "sub",
        "name": prefix + "producto", "quantity": 1, "subtotal": 100,
    }]}]}).encode()
    row = csv_rows(download_file("id", payload, "csv_detail")[2])[1]
    assert all(cell.startswith("'") for cell in row[:3])
    assert row[3:] == ["1", "100"]


def test_zip_contains_exact_individual_files(tmp_path):
    app = make_app(tmp_path / "globals.json")
    journey_id = prepare(app)
    payload = app.state.store.close_journey()
    filename, media, body = download_file(journey_id, payload, "zip")
    assert filename == f"jornada-{journey_id}.zip" and media == "application/zip"
    with ZipFile(BytesIO(body)) as archive:
        assert len(archive.namelist()) == 3
        for format in ("json", "csv_summary", "csv_detail"):
            name, _, content = download_file(journey_id, payload, format)
            assert archive.read(name) == content
        assert archive.testzip() is None


@pytest.mark.parametrize("format", ["json", "csv_summary", "csv_detail", "zip"])
def test_download_endpoint_is_repeatable_without_recounting(tmp_path, format):
    app = make_app(tmp_path / "globals.json")
    journey_id = prepare(app)
    status, headers, _ = request(app, "POST", "/ui/journey", {
        "action": "close", "confirm": "yes", "journey_id": journey_id,
    }, form=True)
    assert status == 303
    status, _, page = request(app, "GET", headers["location"])
    assert status == 200 and 'value="zip" checked' in page
    assert 'class="export-downloads"' not in page
    status, _, records = request(app, "GET", "/registros")
    assert status == 200 and '<details class="export-downloads">' in records
    assert '<details class="export-downloads" open' not in records
    store = app.state.store
    original = store.get_globals()
    disk = store.global_file.read_bytes()
    url = f"/api/exports/last?journey_id={journey_id}&format={format}"
    for _ in range(2):
        status, headers, body = request(app, "GET", url, raw=True)
        assert status == 200 and body
        assert journey_id in headers["content-disposition"]
        assert headers["content-type"].startswith(
            {"json": "application/json", "zip": "application/zip"}.get(format, "text/csv")
        )
    assert store.get_globals() == original
    assert store.global_file.read_bytes() == disk
    store.create_journey("Siguiente")
    assert request(app, "GET", url, raw=True)[0] == 200
    store.close_journey()
    assert request(app, "GET", url, raw=True)[0] == 404
    assert request(app, "GET", f"/exportaciones?journey_id={journey_id}")[0] == 404


def test_invalid_format_missing_export_and_restart(tmp_path):
    app = make_app(tmp_path / "globals.json")
    assert request(app, "GET", "/api/exports/last?format=zip", raw=True)[0] == 404
    prepare(app)
    payload = app.state.store.close_journey()
    assert request(app, "GET", "/api/exports/last?format=invalid")[0] == 422
    assert request(app, "GET", "/api/exports/last", raw=True)[2] == payload
    new_app = make_app(tmp_path / "globals.json")
    assert request(new_app, "GET", "/api/exports/last?format=zip", raw=True)[0] == 404
