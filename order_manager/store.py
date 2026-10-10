"""Lógica de jornadas y catálogo con confirmación persistente por operación."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from functools import wraps
import json
import logging
from pathlib import Path
from threading import RLock
from uuid import uuid4

from .article_search import article_identity
from .journey_export import build_export
from .seed_inventory import initial_inventory
from .persistence import RevisionStorage, StorageError
from .state_validation import validate_state
from .runtime_logging import LogConfig, RuntimeLog


MAX_INPUT_INTEGER = 2**63 - 1


class DomainError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def bounded_integer(value: object, minimum: int, message: str) -> int:
    try:
        if isinstance(value, bool) or not str(value).isdecimal():
            raise DomainError(message)
        number = int(value)
    except ValueError:
        raise DomainError(f"{message} Máximo permitido: {MAX_INPUT_INTEGER}.") from None
    if number < minimum:
        raise DomainError(message)
    if number > MAX_INPUT_INTEGER:
        raise DomainError(f"{message} Máximo permitido: {MAX_INPUT_INTEGER}.")
    return number


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


def mutating(method):
    """Publica una acción completa bajo el mismo bloqueo usado por las consultas."""
    @wraps(method)
    def execute(self, *args, **kwargs):
        with self.lock:
            self._ensure_storage()
            before = self._state()
            self._action_events = []
            context = {"journey_id": (self.journey or {}).get("id"), "revision": self.storage.revision}
            self.runtime_log.record(logging.DEBUG, "Inicio de acción.", method.__name__, phase="mutation", **context)
            phase = "mutation"
            try:
                result = method(self, *args, **kwargs)
                phase = "persistence"
                committed = self.storage.commit(self._state(), method.__name__, self._action_events)
                self._operation = committed["operation"]
                self.runtime_log.record(logging.INFO, "Acción confirmada.", method.__name__,
                                        journey_id=(self.journey or {}).get("id") or context["journey_id"],
                                        revision=self.storage.revision)
                return result
            except Exception as error:
                self._restore(before)
                if not isinstance(error, DomainError):
                    self.runtime_log.record(logging.ERROR, "La acción no pudo confirmarse.", method.__name__,
                                            error=error, phase=phase, **context)
                else:
                    self.runtime_log.record(logging.DEBUG, "Acción rechazada por validación.", method.__name__,
                                            status=error.status, **context)
                if isinstance(error, (OSError, StorageError)):
                    raise DomainError(
                        "No se pudo confirmar el guardado. Revise el almacenamiento antes de reintentar.", 503,
                    ) from error
                raise
            finally:
                self._action_events = []
    return execute


class Store:
    def __init__(self, global_file: Path, *, log_config: LogConfig | None = None):
        self.lock = RLock()
        self.journey: dict | None = None
        self.last_export: tuple[str, bytes] | None = None
        self._new_catalog_articles: dict[str, dict] = {}
        self._price_changes: list[dict] = []
        self._journey_catalog_keys: set[tuple[str, str, str]] = set()
        self.global_file = global_file
        self.inventory_file = global_file.parent / "inventory.json"
        self.data_dir = global_file.parent.resolve()
        self.runtime_log = RuntimeLog(self.data_dir, log_config)
        self.storage = RevisionStorage(self.data_dir, runtime_log=self.runtime_log)
        self.rollback: dict | None = None
        self._export_close_id: str | None = None
        self._operation: dict | None = None
        self._action_events: list[dict] = []
        self.globals = fresh_globals()
        self.inventory = initial_inventory()
        loaded = self.storage.load()
        if loaded is not None:
            self._restore(loaded)
        elif not self.storage.blocked:
            try:
                legacy = global_file.exists() or self.inventory_file.exists()
                if legacy and not self.inventory_file.exists():
                    raise ValueError("Falta el inventario de la instalación existente.")
                if global_file.exists():
                    self.globals = migrate_article_statistics(json.loads(global_file.read_text()))
                if self.inventory_file.exists():
                    self.inventory = json.loads(self.inventory_file.read_text())
                validate_state(self._state())
                committed = self.storage.commit(self._state(), "migration" if legacy else "initialize", [])
                self._operation = committed["operation"]
            except (OSError, ValueError, KeyError, TypeError, StorageError) as error:
                self.runtime_log.record(logging.ERROR, "Inicialización o migración fallida.", "storage_initialize", error=error)
                self.storage.blocked = True
                self.storage.warn("Los datos no pudieron inicializarse o migrarse. Restaure archivos válidos antes de operar.")

        self.runtime_log.record(logging.INFO, "Aplicación inicializada.", "startup",
                                revision=self.storage.revision, phase="blocked" if self.storage.blocked else "ready")

    def _ensure_storage(self) -> None:
        if self.storage.blocked:
            raise DomainError("El almacenamiento requiere recuperación. " + " ".join(self.storage.warnings), 503)

    def _journey_state(self) -> dict:
        return deepcopy({"data": self.journey, "activity": {
            "new_articles": self._new_catalog_articles, "price_changes": self._price_changes,
            "catalog_keys": [list(key) for key in sorted(self._journey_catalog_keys)],
        }})

    def _state(self) -> dict:
        export = None
        if self.last_export:
            export = {"journey_id": self.last_export[0], "close_id": self._export_close_id,
                      "document": json.loads(self.last_export[1])}
        return deepcopy({"inventory": self.inventory, "global_stats": self.globals,
                         "journey": self._journey_state(), "rollback": self.rollback,
                         "last_export": export, "operation": self._operation})

    def _restore(self, state: dict) -> None:
        state = deepcopy(state)
        self.inventory = state["inventory"]
        self.globals = state["global_stats"]
        active = state["journey"]
        self.journey = active["data"]
        self._new_catalog_articles = active["activity"]["new_articles"]
        self._price_changes = active["activity"]["price_changes"]
        self._journey_catalog_keys = {tuple(key) for key in active["activity"]["catalog_keys"]}
        self.rollback = state["rollback"]
        export = state["last_export"]
        self.last_export = (export["journey_id"], json.dumps(export["document"], ensure_ascii=False,
                                                          indent=2).encode()) if export else None
        self._export_close_id = export["close_id"] if export else None
        self._operation = state["operation"]

    def recovery_info(self) -> dict | None:
        with self.lock:
            self._ensure_storage()
            if not self.rollback:
                return None
            target = self.rollback["journey"]["data"]
            return {"journey_id": target["id"], "title": target["title"],
                    "close_id": self.rollback["close_id"], "revision": self.storage.revision,
                    "active_id": self.journey["id"] if self.journey else "",
                    "active_title": self.journey["title"] if self.journey else ""}

    @mutating
    def recover_journey(self, close_id: str, revision: str, active_id: str) -> dict:
        info = self.recovery_info()
        if not info or (close_id, revision, active_id) != (info["close_id"], info["revision"], info["active_id"]):
            raise DomainError("La recuperación cambió. Revise y confirme nuevamente la jornada.", 409)
        snapshot = deepcopy(self.rollback)
        if self.journey:
            self._event("journey_discarded_for_recovery", self.journey["title"])
        active = snapshot["journey"]
        self.journey = active["data"]
        self._new_catalog_articles = active["activity"]["new_articles"]
        self._price_changes = active["activity"]["price_changes"]
        self._journey_catalog_keys = {tuple(k) for k in active["activity"]["catalog_keys"]}
        self.globals = snapshot["globals_before"]
        self.rollback = None
        self.last_export = None
        self._export_close_id = None
        self._event("journey_recovered", self.journey["title"], journey_event=False)
        return deepcopy(self.journey)

    def _active(self, expected_id: str | None = None) -> dict:
        self._ensure_storage()
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

    def _event(self, action: str, detail: str, journey_event: bool = True) -> None:
        entry = {"at": now(), "action": action, "detail": detail}
        journey = self._active()
        if journey_event:
            journey["events"].append(entry)
        self._action_events.append({**entry, "journey_id": journey["id"]})

    def get_events(self) -> list[dict]:
        with self.lock:
            self._ensure_storage()
            return self.storage.history((self._operation or {}).get("pending_events", []))

    def get_journey(self) -> dict | None:
        with self.lock:
            self._ensure_storage()
            return deepcopy(self.journey)

    def get_globals(self) -> dict:
        with self.lock:
            self._ensure_storage()
            return deepcopy(self.globals)

    def get_inventory(self) -> dict:
        with self.lock:
            self._ensure_storage()
            return deepcopy(self.inventory)

    def get_order_inventory(self, order_id: str = "") -> dict:
        """Incluye las categorías originales solo al editar su orden."""
        with self.lock:
            self._ensure_storage()
            inventory = deepcopy(self.inventory)
            if order_id:
                order = self._find(self._active()["orders"], order_id, "Orden")
                for line in order["lines"]:
                    self._register_taxonomy(inventory, deepcopy(line))
            return inventory

    def get_available_articles(self) -> list[dict]:
        with self.lock:
            journey = self._active()
            return deepcopy(self.inventory["articles"])

    def get_last_export(self, expected_id: str | None = None, close_id: str | None = None) -> tuple[str, bytes]:
        with self.lock:
            self._ensure_storage()
            if self.last_export is None:
                raise DomainError("Todavía no hay una jornada exportada.", 404)
            if expected_id is not None and self.last_export[0] != expected_id:
                raise DomainError("La exportación de esta jornada ya no está disponible.", 404)
            if close_id is not None and close_id != self._export_close_id:
                raise DomainError("Los archivos de este cierre ya no están disponibles.", 404)
            return self.last_export

    @mutating
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

    @mutating
    def rename_journey(self, title: str, expected_id: str | None = None) -> dict:
        with self.lock:
            journey = self._active(expected_id)
            title = title.strip()
            if not title:
                raise DomainError("El nombre de la jornada es obligatorio.")
            journey["title"] = title
            self._event("journey_renamed", title)
            return deepcopy(self.journey)

    @mutating
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

    @mutating
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

    @mutating
    def delete_author(self, author_id: str) -> None:
        with self.lock:
            j = self._active()
            item = self._find(j["authors"], author_id, "Autor")
            affected = sum(o["author_id"] == author_id for o in j["orders"])
            if affected:
                raise DomainError("El autor tiene órdenes; elimínelas o asígnelas antes.", 409)
            j["authors"].remove(item)
            self._event("author_deleted", item["name"])

    @mutating
    def add_article(self, data: dict) -> dict:
        with self.lock:
            journey = self._active()
            item = self._article_data(data, allow_empty_price=True)
            item["id"] = str(uuid4())
            inventory = deepcopy(self.inventory)
            inventory["articles"].append(item)
            self._register_taxonomy(inventory, item)
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
        price = bounded_integer(raw_price, 0, "El precio debe ser un número natural.")
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
        article["category"] = category["name"]
        subcategory_name = article["subcategory"]
        subcategory = next(
            (item for item in inventory["subcategories"]
             if item["category_id"] == category["id"]
             and item["name"].casefold() == subcategory_name.casefold()),
            None,
        )
        if subcategory is None:
            subcategory = {
                "id": str(uuid4()),
                "name": subcategory_name,
                "category_id": category["id"],
            }
            inventory["subcategories"].append(subcategory)
        article["subcategory"] = subcategory["name"]

    @mutating
    def update_article(self, article_id: str, data: dict) -> dict:
        with self.lock:
            journey = self._active()
            item = self._find(self.inventory["articles"], article_id, "Artículo")
            updated = self._article_data(data, allow_empty_price=True)
            previous_price = item["unit_price"]
            inventory = deepcopy(self.inventory)
            stored = self._find(inventory["articles"], article_id, "Artículo")
            self._register_taxonomy(inventory, updated)
            stored.update(updated)
            self.inventory = inventory
            item.update(updated)
            for current in journey["articles"]:
                if current["id"] == article_id:
                    current.update(updated)
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

    @mutating
    def delete_article(self, article_id: str) -> None:
        with self.lock:
            j = self._active()
            item = self._find(self.inventory["articles"], article_id, "Artículo")
            inventory = deepcopy(self.inventory)
            stored = self._find(inventory["articles"], article_id, "Artículo")
            inventory["articles"].remove(stored)
            self.inventory = inventory
            j["articles"] = [a for a in j["articles"] if a["id"] != article_id]
            if article_id in self._new_catalog_articles:
                self._new_catalog_articles[article_id]["deleted"] = True
            self._event("article_deleted", item["name"])

    def _lines(self, lines: list[dict], not_billed: bool = False, previous: list[dict] | None = None) -> list[dict]:
        if not lines:
            raise DomainError("La orden necesita al menos un artículo.")
        if len(lines) > 50:
            raise DomainError("La orden admite hasta 50 líneas.")
        output = []
        available = None
        for index, row in enumerate(lines):
            quantity = bounded_integer(
                row.get("quantity"), 1, "La cantidad debe ser un entero positivo.",
            )
            if row.get("catalog_id"):
                if available is None:
                    available = {item["id"]: item for item in self.get_available_articles()}
                old = previous[index] if previous and index < len(previous) else None
                saved_line = old if old and old.get("catalog_id") == row["catalog_id"] else None
                article = available.get(row["catalog_id"]) or saved_line
                if article is None:
                    raise DomainError("Artículo no encontrado.", 404)
                data = {
                    key: article[key]
                    for key in ("name", "category", "subcategory", "unit_price")
                }
                if saved_line:
                    data = {key: old[key] for key in ("name", "category", "subcategory", "unit_price")}
                    if row.get("unit_price") not in (None, ""):
                        data["unit_price"] = row["unit_price"]
                if not_billed:
                    data["unit_price"] = None
                elif data["unit_price"] is None:
                    data = self._article_data({
                        **data,
                        "unit_price": row.get("unit_price"),
                    })
                else:
                    data = self._article_data(data)
            else:
                data = self._article_data(
                    {**row, "unit_price": None} if not_billed else row,
                    allow_empty_price=not_billed,
                )
            output.append({
                **data,
                **({"catalog_id": row["catalog_id"]} if row.get("catalog_id") else {}),
                "quantity": quantity,
                "subtotal": None if not_billed else quantity * data["unit_price"],
            })
        return output

    @mutating
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
            normalized = self._lines(lines, not_billed=status == "not_billed",
                                     previous=existing_order["lines"] if existing_order else None)
            for row in normalized:
                historical_line = existing_order and any(
                    article_identity(old) == article_identity(row) for old in existing_order["lines"]
                )
                if historical_line or any(article_identity(a) == article_identity(row) for a in self.inventory["articles"]):
                    continue
                article = {key: row[key] for key in ("name", "category", "subcategory", "unit_price")}
                article["id"] = str(uuid4())
                self._register_taxonomy(self.inventory, article)
                self.inventory["articles"].append(article)
                j["articles"].append(deepcopy(article))
                self._new_catalog_articles[article["id"]] = {**deepcopy(article), "temporary": False, "deleted": False}
                self._journey_catalog_keys.add(article_identity(article))
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

    @mutating
    def delete_order(self, order_id: str) -> None:
        with self.lock:
            j = self._active()
            order = self._find(j["orders"], order_id, "Orden")
            j["orders"].remove(order)
            self._event("order_deleted", f'Orden {order["number"]}')

    def get_summary(self) -> dict:
        with self.lock:
            return summary(self._active())

    @mutating
    def close_journey(self, expected_id: str | None = None) -> bytes:
        with self.lock:
            j = self._active(expected_id)
            stats = summary(j)
            new_articles = list(self._new_catalog_articles.values())
            try:
                export = build_export(j, stats, new_articles, self._price_changes, now())
                payload = json.dumps(export, ensure_ascii=False, indent=2).encode("utf-8")
            except Exception as error:
                self.runtime_log.record(logging.ERROR, "Falló la generación de la exportación de cierre.",
                                        "export_failed", error=error, journey_id=j["id"], format="json")
                raise
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
            close_id = uuid4().hex
            self.rollback = {"close_id": close_id, "journey": self._journey_state(),
                             "globals_before": deepcopy(self.globals)}
            self._event("journey_closed", j["title"], journey_event=False)
            self._export_close_id = close_id
            self.globals = next_globals
            self.last_export = (j["id"], payload)
            self.journey = None
            self._clear_article_activity()
            return payload

    @mutating
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
