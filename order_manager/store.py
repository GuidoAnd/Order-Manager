"""Estado temporal de jornada y acumulados globales en JSON."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock
from uuid import uuid4


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
        "closed_ids": [],
    }


def summary(journey: dict) -> dict:
    orders = journey["orders"]
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
            article_key = f'{line["category"]} / {line["subcategory"]} / {line["name"]}'
            groups = (
                (result["by_category"], line["category"]),
                (result["by_article"], article_key),
            )
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
        self.events: list[dict] = []
        self.last_export: tuple[str, bytes] | None = None
        self.global_file = global_file
        if global_file.exists():
            self.globals = json.loads(global_file.read_text())
        else:
            self.globals = fresh_globals()

    def _active(self) -> dict:
        if self.journey is None:
            raise DomainError("No hay jornada activa.", 409)
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
        self.events.append(entry)

    def get_events(self) -> list[dict]:
        with self.lock:
            return deepcopy(self.events)

    def get_journey(self) -> dict | None:
        with self.lock:
            return deepcopy(self.journey)

    def get_globals(self) -> dict:
        with self.lock:
            return deepcopy(self.globals)

    def get_last_export(self) -> tuple[str, bytes]:
        with self.lock:
            if self.last_export is None:
                raise DomainError("Todavía no hay una jornada exportada.", 404)
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
                "articles": [],
                "orders": [],
                "events": [],
                "next_order": 1,
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
            self._active()
            item = self._article_data(data)
            item["id"] = str(uuid4())
            self.journey["articles"].append(item)
            self._event("article_created", item["name"])
            return deepcopy(item)

    @staticmethod
    def _article_data(data: dict) -> dict:
        values = {
            key: str(data.get(key) or "").strip()
            for key in ("name", "category", "subcategory")
        }
        if not all(values.values()):
            raise DomainError("Nombre, categoría y subcategoría son obligatorios.")
        raw_price = data.get("unit_price")
        if isinstance(raw_price, bool) or not str(raw_price).isdecimal():
            raise DomainError("El precio debe ser un número natural.")
        price = int(raw_price)
        if price < 0:
            raise DomainError("El precio debe ser un número natural.")
        return {**values, "unit_price": price}

    def update_article(self, article_id: str, data: dict) -> dict:
        with self.lock:
            item = self._find(self._active()["articles"], article_id, "Artículo")
            item.update(self._article_data(data))
            self._event("article_updated", item["name"])
            return deepcopy(item)

    def delete_article(self, article_id: str) -> None:
        with self.lock:
            j = self._active()
            item = self._find(j["articles"], article_id, "Artículo")
            j["articles"].remove(item)
            self._event("article_deleted", item["name"])

    def _lines(self, lines: list[dict]) -> list[dict]:
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
                article = self._find(self._active()["articles"], row["catalog_id"], "Artículo")
                data = {
                    key: article[key]
                    for key in ("name", "category", "subcategory", "unit_price")
                }
            else:
                data = self._article_data(row)
            output.append({
                **data,
                "quantity": quantity,
                "subtotal": quantity * data["unit_price"],
            })
        return output

    def save_order(self, author_id: str, lines: list[dict], order_id: str | None = None) -> dict:
        with self.lock:
            j = self._active()
            self._find(j["authors"], author_id, "Autor")
            normalized = self._lines(lines)
            if order_id:
                order = self._find(j["orders"], order_id, "Orden")
                order.update({
                    "author_id": author_id,
                    "lines": normalized,
                    "total": sum(row["subtotal"] for row in normalized),
                    "updated_at": now(),
                })
                action = "order_updated"
            else:
                order = {
                    "id": str(uuid4()),
                    "number": j["next_order"],
                    "author_id": author_id,
                    "lines": normalized,
                    "total": sum(row["subtotal"] for row in normalized),
                    "created_at": now(),
                }
                j["next_order"] += 1
                j["orders"].append(order)
                action = "order_created"
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

    def _write_globals(self, data: dict) -> None:
        self.global_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.global_file.parent,
                prefix=".globals-",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.global_file)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()

    def close_journey(self) -> bytes:
        with self.lock:
            j = self._active()
            stats = summary(j)
            export = deepcopy(j)
            export["closed_at"] = now()
            export["statistics"] = stats
            export["events"].append({
                "at": export["closed_at"],
                "action": "journey_closed",
                "detail": j["title"],
            })
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
            self.events.append(export["events"][-1])
            self.last_export = (j["id"], payload)
            self.journey = None
            return payload

    def discard_journey(self) -> None:
        with self.lock:
            title = self._active()["title"]
            self._event("journey_discarded", title)
            self.journey = None
