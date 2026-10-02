"""CSV de ventas y paquete ZIP derivados del JSON de una jornada cerrada."""

import csv
from io import BytesIO, StringIO
import json
from typing import Literal
from zipfile import ZIP_DEFLATED, ZipFile


ExportFormat = Literal["json", "csv_summary", "csv_detail", "zip"]


def sold_articles(export: dict) -> list[dict]:
    articles = {}
    for order in export["orders"]:
        if order.get("status", "sale") != "sale":
            continue
        for line in order["lines"]:
            key = tuple(line[field] for field in ("category", "subcategory", "name"))
            item = articles.setdefault(key, {
                "category": key[0], "subcategory": key[1], "name": key[2],
                "units": 0, "revenue": 0,
            })
            item["units"] += line["quantity"]
            item["revenue"] += line["subtotal"]
    return sorted(articles.values(), key=lambda item: tuple(
        item[field].casefold() for field in ("category", "subcategory", "name")
    ))


def _csv_bytes(rows: list[list]) -> bytes:
    output = StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    for row in rows:
        # Conserva nombres como texto cuando una planilla podría evaluarlos.
        writer.writerow([
            "'" + value if isinstance(value, str)
            and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n"))
            else value
            for value in row
        ])
    return output.getvalue().encode("utf-8-sig")


def summary_csv(articles: list[dict]) -> bytes:
    categories = {}
    for article in articles:
        categories.setdefault(article["category"], []).append(article)
    rows = []
    for category, items in categories.items():
        rows.append([category, *[
            f"{item['name']} [{item['subcategory']}]" for item in items
        ]])
        rows.append(["Unidades", *[item["units"] for item in items]])
    if not rows:
        rows = [["Categoría / artículo"]]
    width = max(len(row) for row in rows)
    return _csv_bytes([row + [""] * (width - len(row)) for row in rows])


def detail_csv(articles: list[dict]) -> bytes:
    rows = [["Categoría", "Subcategoría", "Artículo", "Unidades", "Importe"]]
    rows.extend([
        item[field] for field in ("category", "subcategory", "name", "units", "revenue")
    ] for item in articles)
    return _csv_bytes(rows)


def download_file(
    journey_id: str, payload: bytes, file_format: ExportFormat,
) -> tuple[str, str, bytes]:
    base = f"jornada-{journey_id}"
    if file_format == "json":
        return f"{base}.json", "application/json", payload
    articles = sold_articles(json.loads(payload))
    if file_format == "csv_summary":
        return f"{base}-resumen.csv", "text/csv", summary_csv(articles)
    if file_format == "csv_detail":
        return f"{base}-detalle.csv", "text/csv", detail_csv(articles)
    if file_format != "zip":
        raise ValueError("Formato de exportación desconocido.")
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(f"{base}.json", payload)
        archive.writestr(f"{base}-resumen.csv", summary_csv(articles))
        archive.writestr(f"{base}-detalle.csv", detail_csv(articles))
    return f"{base}.zip", "application/zip", output.getvalue()
