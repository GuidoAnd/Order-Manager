"""Borradores acotados y navegación GET del editor, sin modificar el estado confirmado."""

from collections import OrderedDict
from copy import deepcopy
import json
from secrets import token_urlsafe
from threading import RLock
from time import monotonic

from fastapi import Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from . import web
from .store import DomainError
from .order_picker import register_order_picker
from .notices import order_details


class EditorDrafts:
    lifetime = 1800
    max_entries = 128
    max_bytes = 8 * 1024 * 1024

    def __init__(self):
        self.lock = RLock()
        self.entries = OrderedDict()

    def _expire(self):
        for key, entry in list(self.entries.items()):
            if monotonic() - entry["session"]["created"] >= self.lifetime:
                del self.entries[key]

    def put(self, session, values, rows=None, error="", status=200, *, picker=None):
        self._expire()
        entry = dict(session=session, values=deepcopy(values), rows=deepcopy(rows),
                     error=error, status=status)
        if picker is not None:
            entry["picker"] = deepcopy(picker)
            entry["picker"]["flow"] = picker["flow"]
        size = len(json.dumps(entry, ensure_ascii=True).encode())
        if size > self.max_bytes:
            raise DomainError("El borrador excede el tamaño permitido.", 413)
        while self.entries and (len(self.entries) >= self.max_entries or
                                sum(item["size"] for item in self.entries.values()) + size > self.max_bytes):
            self.entries.popitem(last=False)
        key = token_urlsafe(24)
        entry["size"] = size
        self.entries[key] = entry
        return key

    def get(self, key):
        self._expire()
        if key not in self.entries:
            raise DomainError("El borrador venció o ya no está disponible. Abra un editor nuevo; "
                              "las órdenes guardadas se conservan.", 409)
        self.entries.move_to_end(key)
        return self.entries[key]


def order_form_rows(values: dict, count: int, inventory: dict) -> list[dict]:
    rows = []
    for index in range(count):
        row = {
            key: values.get(f"{key}_{index}", "")
            for key in (
                "source", "catalog_id", "line_id", "name", "category", "quantity",
                "unit_price", "new_unit_price",
            )
        }
        row["subcategories"] = {
            str(position): values.get(f"subcategory_{index}_{position}", "")
            for position in range(len(inventory["categories"]))
        }
        row["subcategory"] = next(
            (row["subcategories"][str(position)]
             for position, category in enumerate(inventory["categories"])
             if category["name"] == row["category"]),
            "",
        )
        rows.append(row)
    return rows


def order_form_lines(rows: list[dict], inventory: dict) -> list[dict]:
    lines = []
    for index, row in enumerate(rows, start=1):
        if row["source"] == "inventory":
            if not row["catalog_id"]:
                raise DomainError(f"Artículo {index}: selecciona un artículo del inventario.")
            line = {
                key: row[key] for key in ("catalog_id", "quantity", "unit_price")
            }
        elif row["source"] == "new":
            category = next(
                (item for item in inventory["categories"] if item["name"] == row["category"]),
                None,
            )
            if category is None:
                raise DomainError(f"Artículo {index}: selecciona una categoría existente.")
            if not any(
                item["category_id"] == category["id"] and item["name"] == row["subcategory"]
                for item in inventory["subcategories"]
            ):
                raise DomainError(f"Artículo {index}: selecciona una subcategoría de esa categoría.")
            line = {
                key: row[key] for key in ("name", "category", "subcategory", "quantity")
            }
            line["unit_price"] = row["new_unit_price"]
        else:
            raise DomainError(f"Artículo {index}: elige Del inventario o Nuevo producto.")
        if row.get("line_id"):
            line["line_id"] = row["line_id"]
        lines.append(line)
    return lines


def register_order_editor(app, store, fields, notices):
    drafts = EditorDrafts()
    app.state.order_drafts = drafts
    open_picker = register_order_picker(app, store, fields, drafts)

    def redirect_draft(session, values, rows=None, error="", status=200):
        key = drafts.put(session, values, rows, error, status)
        return RedirectResponse("/ordenes/borrador/" + key, status_code=303)

    def render_draft(key):
        entry = drafts.get(key)
        session, values = entry["session"], entry["values"]
        if session["result"]:
            return RedirectResponse(session["result"], status_code=303)
        return HTMLResponse(web.orders_page(
            store, rows=entry["rows"], author_id=values.get("author_id", ""),
            edit_id=session["order_id"], error=entry["error"], editor=True,
            order_status=values.get("order_status"), series=values.get("series"),
            serial_number=values.get("serial_number"),
            page=values.get("page", 1), article_id=values.get("article", ""),
            query=values.get("q", ""), search_by=values.get("search_by", "all"),
            editor_token=key, editor_context=session["context"],
        ), status_code=entry["status"])

    def start(order_id, page, article, q, search_by):
        with drafts.lock, store.lock:
            journey = store.get_journey()
            if not journey:
                return web.orders_page(store, editor=True)
            order = next((o for o in journey["orders"] if o["id"] == order_id), None)
            if order_id and order is None:
                raise DomainError("Orden no encontrada.", 404)
            session = dict(created=monotonic(), journey_id=journey["id"], order_id=order_id,
                           original=deepcopy(order), result="", context={
                               "journey": {"id": journey["id"], "authors": journey["authors"],
                                           "orders": [order] if order else []},
                               "inventory": store.get_order_inventory(order_id),
                           })
            key = drafts.put(session, dict(page=page, article=article, q=q, search_by=search_by))
            return render_draft(key)

    @app.get("/ordenes/nueva", response_class=HTMLResponse)
    def new_order(page: int = Query(default=1, ge=1), article: str = "", q: str = "",
                  search_by: str = "all"):
        return start("", page, article, q, search_by)

    @app.get("/ordenes/{order_id}/editar", response_class=HTMLResponse)
    def edit_order(order_id: str, page: int = Query(default=1, ge=1), article: str = "", q: str = "",
                  search_by: str = "all"):
        return start(order_id, page, article, q, search_by)

    @app.get("/ordenes/borrador/{draft_id}")
    def draft_page(draft_id: str):
        with drafts.lock:
            return render_draft(draft_id)

    @app.post("/ui/orders/form")
    async def order_form(request: Request):
        values = await fields(request)
        with drafts.lock, store.lock:
            entry = drafts.get(values.get("editor_token", ""))
            session = entry["session"]
            if session["result"]:
                return RedirectResponse(session["result"], status_code=303)
            if values.get("order_id", "") != session["order_id"]:
                raise DomainError("El formulario no corresponde a esta orden.", 409)
            # Nunca guardar CSRF ni tokens anteriores dentro del borrador.
            values = {k: v for k, v in values.items() if k not in {"csrf_token", "editor_token"}}
            try:
                page = max(1, int(values.get("page", "1")))
            except ValueError:
                page = 1
            values["page"] = page
            rows = None
            try:
                count = int(values.get("count", "1"))
                if count < 1 or count > 50:
                    raise DomainError("Número de líneas inválido.")
                inventory = session["context"]["inventory"]
                rows = order_form_rows(values, count, inventory)
                journey = store.get_journey()
                if not journey or journey["id"] != session["journey_id"]:
                    raise DomainError("La jornada cambió. El borrador no se guardó.", 409)
                action = values.get("action", "")
                if action == "pick" or action.startswith("pick_"):
                    target = None if action == "pick" else int(action.split("_", 1)[1])
                    if target is not None and not 0 <= target < len(rows):
                        raise DomainError("Artículo no válido.")
                    return open_picker(session, values, rows, target)
                if action == "add":
                    if len(rows) == 50:
                        raise DomainError("La orden admite hasta 50 líneas.")
                    rows.append({})
                elif action.startswith("remove_"):
                    index = int(action.split("_", 1)[1])
                    if not 0 <= index < len(rows):
                        raise DomainError("Artículo no válido.")
                    rows.pop(index)
                    if not rows:
                        rows = [{}]
                elif action == "save":
                    if session["order_id"]:
                        current = next((o for o in journey["orders"] if o["id"] == session["order_id"]), None)
                        if current != session["original"]:
                            raise DomainError("La orden cambió o fue eliminada desde que abrió el editor. "
                                              "No se guardaron sus cambios. Abra la versión actual para compararla.", 409)
                    order = store.save_order(
                        values.get("author_id", ""), order_form_lines(rows, inventory),
                        session["order_id"] or None, status=values.get("order_status", "sale"),
                        series=values.get("series", ""), serial_number=values.get("serial_number", ""),
                    )
                    target = web.orders_url(page, values.get("article", ""), values.get("q", ""),
                                            values.get("search_by", "all")) + "#order-results"
                    code = "order_updated" if session["order_id"] else "order_created"
                    session["result"] = notices.url(target, code, **order_details(order, journey))
                    return RedirectResponse(session["result"], status_code=303)
                else:
                    raise DomainError("Acción no reconocida.")
                return redirect_draft(session, values, rows)
            except (DomainError, ValueError, IndexError) as error:
                status = error.status if isinstance(error, DomainError) else 400
                message = str(error) if isinstance(error, DomainError) else "Datos de línea inválidos."
                return redirect_draft(session, values, rows, message, status)
