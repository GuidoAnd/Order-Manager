"""Estado temporal de jornada y acumulados globales en JSON."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock
from uuid import NAMESPACE_URL, uuid4, uuid5

from .article_search import article_identity
from .journey_export import build_export
from .seed_inventory import initial_inventory


class DomainError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fresh_globals() -> dict:
    return {
        "journeys": 0,
        "orders": 0,
        "units": 0,
        "revenue": 0,
        "by_category": {},
        "by_article": {},
        "article_key_format": "escaped-v1",
        "closed_ids": [],
    }


def article_statistics_key(parts: list[str]) -> str:
    """Escapa cada campo para que sus barras no se confundan con separadores."""
    return " / ".join(part.replace("\\", "\\\\").replace("/", "\\/") for part in parts)


def migrate_article_statistics(data: dict) -> dict:
    if data.get("article_key_format") == "escaped-v1":
        return data
    migrated = deepcopy(data)
    articles = {}
    for key, totals in migrated["by_article"].items():
        parts = key.split(" / ")
        # Un acumulado antiguo ambiguo no permite reconstruir sus artículos.
        new_key = article_statistics_key(parts) if len(parts) == 3 else key
        articles[new_key] = totals
    migrated["by_article"] = articles
    migrated["article_key_format"] = "escaped-v1"
    return migrated


def is_sale(order: dict) -> bool:
    return order.get("status", "sale") == "sale"


def summary(journey: dict) -> dict:
    orders = [order for order in journey["orders"] if is_sale(order)]
    result = {
        "orders": len(orders),
        "units": 0,
        "revenue": 0,
        "by_category": {},
        "by_article": {},
        "by_author": {},
    }
    for author in journey["authors"]:
        result["by_author"][author["id"]] = {
            "name": author["name"],
            "orders": 0,
            "units": 0,
            "revenue": 0,
            "average": 0,
            "by_article": {},
        }
    for order in orders:
        author = result["by_author"].get(order["author_id"])
        if author:
            author["orders"] += 1
            author["revenue"] += order["total"]
        for line in order["lines"]:
            qty, revenue = line["quantity"], line["subtotal"]
            result["units"] += qty
            result["revenue"] += revenue
            if author:
                author["units"] += qty
            article_key = article_statistics_key([
                line["category"], line["subcategory"], line["name"],
            ])
            groups = (
                (result["by_category"], line["category"]),
                (result["by_article"], article_key),
            )
            if author:
                groups += ((author["by_article"], article_key),)
            for container, key in groups:
                item = container.setdefault(key, {"units": 0, "revenue": 0})
                item["units"] += qty
                item["revenue"] += revenue
    for author in result["by_author"].values():
        if author["orders"]:
            author["average"] = author["revenue"] / author["orders"]
    return result


class Store:
    def __init__(self, global_file: Path):
        self.lock = RLock()
        self.journey: dict | None = None
        self.last_export: tuple[str, bytes] | None = None
        self._new_catalog_articles: dict[str, dict] = {}
        self._price_changes: list[dict] = []
        self._journey_catalog_keys: set[tuple[str, str, str]] = set()
        self.global_file = global_file
        self.inventory_file = global_file.parent / "inventory.json"
        if global_file.exists():
            self.globals = migrate_article_statistics(json.loads(global_file.read_text()))
        else:
            self.globals = fresh_globals()
        if self.inventory_file.exists():
            self.inventory = json.loads(self.inventory_file.read_text())
        else:
            self.inventory = initial_inventory()
            self._write_inventory(self.inventory)

    def _active(self, expected_id: str | None = None) -> dict:
        if self.journey is None:
            raise DomainError("No hay jornada activa.", 409)
        if expected_id is not None and self.journey["id"] != expected_id:
            raise DomainError(
                "La jornada cambió. Revise la jornada actual antes de confirmar.", 409,
            )
        return self.journey

    @staticmethod
    def _find(items: list[dict], item_id: str, name: str) -> dict:
        for item in items:
            if item["id"] == item_id:
                return item
        raise DomainError(f"{name} no encontrado.", 404)

    def _event(self, action: str, detail: str) -> None:
        entry = {"at": now(), "action": action, "detail": detail}
        self._active()["events"].append(entry)

    def get_events(self) -> list[dict]:
        with self.lock:
            return deepcopy(self.journey["events"]) if self.journey else []

    def get_journey(self) -> dict | None:
        with self.lock:
            return deepcopy(self.journey)

    def get_globals(self) -> dict:
        with self.lock:
            return deepcopy(self.globals)

    def get_inventory(self) -> dict:
        with self.lock:
            return deepcopy(self.inventory)

    def get_available_articles(self) -> list[dict]:
        with self.lock:
            journey = self._active()
            return deepcopy(journey["articles"] + self._temporary_articles(journey))

    @staticmethod
    def _temporary_articles(journey: dict) -> list[dict]:
        def article_key(article: dict) -> tuple[str, str, str]:
            return tuple(
                article[field].casefold()
                for field in ("category", "subcategory", "name")
            )

        catalog_keys = {article_key(article) for article in journey["articles"]}
        temporary = {}
        for order in journey["orders"]:
            if not is_sale(order):
                continue
            for line in order["lines"]:
                key = article_key(line)
                if key in catalog_keys:
                    continue
                identity = json.dumps([journey["id"], *key], ensure_ascii=False)
                temporary[key] = {
                    "id": f"temporary-{uuid5(NAMESPACE_URL, identity).hex}",
                    "name": line["name"],
                    "category": line["category"],
                    "subcategory": line["subcategory"],
                    "unit_price": line["unit_price"],
                    "temporary": True,
                }
        return list(temporary.values())

    def get_last_export(self, expected_id: str | None = None) -> tuple[str, bytes]:
        with self.lock:
            if self.last_export is None:
                raise DomainError("Todavía no hay una jornada exportada.", 404)
            if expected_id is not None and self.last_export[0] != expected_id:
                raise DomainError("La exportación de esta jornada ya no está disponible.", 404)
            return self.last_export

    def create_journey(self, title: str) -> dict:
        with self.lock:
            if self.journey is not None:
                raise DomainError("Cierre o descarte la jornada activa antes de abrir otra.", 409)
            title = title.strip()
            if not title:
                raise DomainError("El nombre de la jornada es obligatorio.")
            self.journey = {
                "id": str(uuid4()),
                "title": title,
                "opened_at": now(),
                "authors": [],
                "articles": deepcopy(self.inventory["articles"]),
                "orders": [],
                "events": [],
                "next_order": 1,
            }
            self._new_catalog_articles = {}
            self._price_changes = []
            self._journey_catalog_keys = {
                article_identity(article) for article in self.journey["articles"]
            }
            self._event("journey_created", title)
            return deepcopy(self.journey)

    def rename_journey(self, title: str) -> dict:
        with self.lock:
            title = title.strip()
            if not title:
                raise DomainError("El nombre de la jornada es obligatorio.")
            self._active()["title"] = title
            self._event("journey_renamed", title)
            return deepcopy(self.journey)

    def add_author(self, name: str) -> dict:
        with self.lock:
            name = name.strip()
            if not name:
                raise DomainError("El nombre del autor es obligatorio.")
            j = self._active()
            if any(a["name"].casefold() == name.casefold() for a in j["authors"]):
                raise DomainError("Ya existe un autor con ese nombre.", 409)
            item = {"id": str(uuid4()), "name": name}
            j["authors"].append(item)
            self._event("author_created", name)
            return deepcopy(item)

    def rename_author(self, author_id: str, name: str) -> dict:
        with self.lock:
            j = self._active()
            item = self._find(j["authors"], author_id, "Autor")
            name = name.strip()
            if not name or any(a["id"] != author_id and a["name"].casefold() == name.casefold()
                               for a in j["authors"]):
                raise DomainError("Nombre de autor vacío o duplicado.")
            item["name"] = name
            self._event("author_updated", name)
            return deepcopy(item)

    def delete_author(self, author_id: str) -> None:
        with self.lock:
            j = self._active()
            item = self._find(j["authors"], author_id, "Autor")
            affected = sum(o["author_id"] == author_id for o in j["orders"])
            if affected:
                raise DomainError("El autor tiene órdenes; elimínelas o asígnelas antes.", 409)
            j["authors"].remove(item)
            self._event("author_deleted", item["name"])

    def add_article(self, data: dict) -> dict:
        with self.lock:
            journey = self._active()
            item = self._article_data(data, allow_empty_price=True)
            item["id"] = str(uuid4())
            inventory = deepcopy(self.inventory)
            inventory["articles"].append(item)
            self._register_taxonomy(inventory, item)
            self._write_inventory(inventory)
            self.inventory = inventory
            journey["articles"].append(item)
            self._new_catalog_articles[item["id"]] = {
                **deepcopy(item), "temporary": False, "deleted": False,
            }
            self._journey_catalog_keys.add(article_identity(item))
            self._event("article_created", item["name"])
            return deepcopy(item)

    @staticmethod
    def _article_data(data: dict, allow_empty_price: bool = False) -> dict:
        values = {
            key: str(data.get(key) or "").strip()
            for key in ("name", "category", "subcategory")
        }
        if not all(values.values()):
            raise DomainError("Nombre, categoría y subcategoría son obligatorios.")
        raw_price = data.get("unit_price")
        if allow_empty_price and raw_price in (None, ""):
            return {**values, "unit_price": None}
        if isinstance(raw_price, bool) or not str(raw_price).isdecimal():
            raise DomainError("El precio debe ser un número natural.")
        price = int(raw_price)
        if price < 0:
            raise DomainError("El precio debe ser un número natural.")
        return {**values, "unit_price": price}

    @staticmethod
    def _register_taxonomy(inventory: dict, article: dict) -> None:
        category_name = article["category"]
        category = next(
            (item for item in inventory["categories"]
             if item["name"].casefold() == category_name.casefold()),
            None,
        )
        if category is None:
            category = {"id": str(uuid4()), "name": category_name}
            inventory["categories"].append(category)
        subcategory_name = article["subcategory"]
        if not any(
            item["category_id"] == category["id"]
            and item["name"].casefold() == subcategory_name.casefold()
            for item in inventory["subcategories"]
        ):
            inventory["subcategories"].append({
                "id": str(uuid4()),
                "name": subcategory_name,
                "category_id": category["id"],
            })

    def update_article(self, article_id: str, data: dict) -> dict:
        with self.lock:
            journey = self._active()
            item = self._find(journey["articles"], article_id, "Artículo")
            updated = self._article_data(data, allow_empty_price=True)
            previous_price = item["unit_price"]
            inventory = deepcopy(self.inventory)
            stored = self._find(inventory["articles"], article_id, "Artículo")
            stored.update(updated)
            self._register_taxonomy(inventory, stored)
            self._write_inventory(inventory)
            self.inventory = inventory
            item.update(updated)
            self._journey_catalog_keys.add(article_identity(item))
            if article_id in self._new_catalog_articles:
                self._new_catalog_articles[article_id].update(deepcopy(item))
            if previous_price != item["unit_price"]:
                self._price_changes.append({
                    "at": now(), "article_id": article_id,
                    "name": item["name"], "category": item["category"],
                    "subcategory": item["subcategory"],
                    "previous_price": previous_price, "new_price": item["unit_price"],
                })
            self._event("article_updated", item["name"])
            return deepcopy(item)

    def delete_article(self, article_id: str) -> None:
        with self.lock:
            j = self._active()
            item = self._find(j["articles"], article_id, "Artículo")
            inventory = deepcopy(self.inventory)
            stored = self._find(inventory["articles"], article_id, "Artículo")
            inventory["articles"].remove(stored)
            self._write_inventory(inventory)
            self.inventory = inventory
            j["articles"].remove(item)
            if article_id in self._new_catalog_articles:
                self._new_catalog_articles[article_id]["deleted"] = True
            self._event("article_deleted", item["name"])

    def _lines(self, lines: list[dict], not_billed: bool = False) -> list[dict]:
        if not lines:
            raise DomainError("La orden necesita al menos un artículo.")
        if len(lines) > 50:
            raise DomainError("La orden admite hasta 50 líneas.")
        output = []
        for row in lines:
            raw_quantity = row.get("quantity")
            if isinstance(raw_quantity, bool) or not str(raw_quantity).isdecimal():
                raise DomainError("La cantidad debe ser un entero positivo.")
            quantity = int(raw_quantity)
            if quantity < 1:
                raise DomainError("La cantidad debe ser un entero positivo.")
            if row.get("catalog_id"):
                article = self._find(
                    self.get_available_articles(), row["catalog_id"], "Artículo"
                )
                data = {
                    key: article[key]
                    for key in ("name", "category", "subcategory", "unit_price")
                }
                if not_billed:
                    data["unit_price"] = None
                elif data["unit_price"] is None:
                    data = self._article_data({
                        **data,
                        "unit_price": row.get("unit_price"),
                    })
            else:
                data = self._article_data(
                    {**row, "unit_price": None} if not_billed else row,
                    allow_empty_price=not_billed,
                )
            output.append({
                **data,
                "quantity": quantity,
                "subtotal": None if not_billed else quantity * data["unit_price"],
            })
        return output

    def save_order(
        self, author_id: str, lines: list[dict], order_id: str | None = None,
        status: str = "sale",
    ) -> dict:
        with self.lock:
            j = self._active()
            if status not in {"sale", "not_billed"}:
                raise DomainError("Estado de la orden inválido.")
            self._find(j["authors"], author_id, "Autor")
            existing_order = (
                self._find(j["orders"], order_id, "Orden") if order_id else None
            )
            normalized = self._lines(lines, not_billed=status == "not_billed")
            total = None if status == "not_billed" else sum(row["subtotal"] for row in normalized)
            if existing_order:
                order = existing_order
                order.update({
                    "author_id": author_id,
                    "lines": normalized,
                    "total": total,
                    "status": status,
                    "updated_at": now(),
                })
                action = "order_updated"
            else:
                order = {
                    "id": str(uuid4()),
                    "number": j["next_order"],
                    "author_id": author_id,
                    "lines": normalized,
                    "total": total,
                    "status": status,
                    "created_at": now(),
                }
                j["next_order"] += 1
                j["orders"].append(order)
                action = "order_created"
            if status == "not_billed":
                articles = ", ".join(
                    f'{line["name"]} × {line["quantity"]}' for line in normalized
                )
                self._event(
                    "order_not_billed",
                    f'Orden #{order["number"]} · ID {order["id"]} · '
                    f'No facturada (regalo/cancelada), sin importe · {articles}',
                )
            else:
                self._event(action, f'Orden {order["number"]}')
            return deepcopy(order)

    def delete_order(self, order_id: str) -> None:
        with self.lock:
            j = self._active()
            order = self._find(j["orders"], order_id, "Orden")
            j["orders"].remove(order)
            self._event("order_deleted", f'Orden {order["number"]}')

    def get_summary(self) -> dict:
        with self.lock:
            return summary(self._active())

    @staticmethod
    def _write_json(path: Path, data: dict, prefix: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=path.parent,
                prefix=prefix,
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()

    def _write_globals(self, data: dict) -> None:
        try:
            self._write_json(self.global_file, data, ".globals-")
        except OSError as error:
            raise DomainError(
                "No se pudo guardar el cierre. La jornada sigue activa y sus datos "
                "se conservan. Puede reintentar cuando se restablezca el almacenamiento.",
                503,
            ) from error

    def _write_inventory(self, data: dict) -> None:
        try:
            self._write_json(self.inventory_file, data, ".inventory-")
        except OSError as error:
            raise DomainError(
                "No se pudo guardar el catálogo. No se aplicaron los cambios. "
                "Puede reintentar cuando se restablezca el almacenamiento.",
                503,
            ) from error

    def close_journey(self, expected_id: str | None = None) -> bytes:
        with self.lock:
            j = self._active(expected_id)
            stats = summary(j)
            new_articles = list(self._new_catalog_articles.values()) + [
                {**article, "deleted": False}
                for article in self._temporary_articles(j)
                if article_identity(article) not in self._journey_catalog_keys
            ]
            export = build_export(j, stats, new_articles, self._price_changes, now())
            payload = json.dumps(export, ensure_ascii=False, indent=2).encode("utf-8")
            next_globals = deepcopy(self.globals)
            if j["id"] not in next_globals["closed_ids"]:
                next_globals["closed_ids"].append(j["id"])
                next_globals["journeys"] += 1
                for key in ("orders", "units", "revenue"):
                    next_globals[key] += stats[key]
                for group in ("by_category", "by_article"):
                    for key, value in stats[group].items():
                        entry = next_globals[group].setdefault(key, {"units": 0, "revenue": 0})
                        for metric in ("units", "revenue"):
                            entry[metric] += value[metric]
            self._write_globals(next_globals)
            self.globals = next_globals
            self.last_export = (j["id"], payload)
            self.journey = None
            self._clear_article_activity()
            return payload

    def discard_journey(self, expected_id: str | None = None) -> None:
        with self.lock:
            title = self._active(expected_id)["title"]
            self._event("journey_discarded", title)
            self.journey = None
            self._clear_article_activity()

    def _clear_article_activity(self) -> None:
        self._new_catalog_articles = {}
        self._price_changes = []
        self._journey_catalog_keys = set()
