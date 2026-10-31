"""API HTTP y rutas de interfaz del gestor de órdenes."""
from __future__ import annotations

import os
import logging
from secrets import token_urlsafe
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import parse_qs, urlencode

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from pydantic import BaseModel, BeforeValidator, Field

from . import journey_results, web
from .article_search import ArticleSearch
from .export_formats import ExportFormat, download_file
from .store import MAX_INPUT_INTEGER, DomainError, Store
from .runtime_logging import LogConfig, RequestDiagnostics
from .journey_navigation import JourneyNavigation
from .order_editor import register_order_editor
from .batch_ui import register_batch_ui
from .health import HealthCheck
from .notices import NoticeContext, OperationNotices, order_details
from .security import LocalSecurity, MAX_FIELDS, parse_allowed_hosts
from .input_validation import bounded_text

ROOT = Path(__file__).resolve().parent.parent


def reject_boolean(value: object) -> object:
    if isinstance(value, bool):
        raise ValueError("El valor debe ser un número entero, no un booleano.")
    return value


NonBooleanInt = Annotated[int, BeforeValidator(reject_boolean)]


class NameInput(BaseModel):
    name: str = Field(min_length=1)


class JourneyInput(BaseModel):
    title: str = Field(min_length=1)


class JourneyConfirmation(BaseModel):
    journey_id: str = Field(min_length=1)


class RecoveryConfirmation(BaseModel):
    close_id: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    active_id: str = ""


class ArticleInput(BaseModel):
    name: str
    category: str
    subcategory: str
    unit_price: NonBooleanInt | None = Field(default=None, ge=0, le=MAX_INPUT_INTEGER)


class LineInput(BaseModel):
    line_id: str | None = Field(default=None, min_length=1, max_length=36)
    catalog_id: str | None = None
    name: str | None = None
    category: str | None = None
    subcategory: str | None = None
    unit_price: NonBooleanInt | None = Field(default=None, ge=0, le=MAX_INPUT_INTEGER)
    quantity: NonBooleanInt = Field(ge=1, le=MAX_INPUT_INTEGER)


class OrderInput(BaseModel):
    series: Literal["10", "20"] | None = None
    batch_id: str | None = None
    serial_number: NonBooleanInt = Field(ge=1, le=160)
    author_id: str
    status: Literal["sale", "not_billed"] = "sale"
    lines: list[LineInput] = Field(min_length=1, max_length=50)



def make_app(global_file: Path | None = None, *, data_dir: Path | None = None,
             log_config: LogConfig | None = None) -> FastAPI:
    if global_file is not None and data_dir is not None:
        raise ValueError("Indique global_file o data_dir, no ambos.")
    allowed_hosts = parse_allowed_hosts(os.environ.get("ALLOWED_HOSTS", ""))
    directory = Path(data_dir or os.environ.get("DATA_DIR") or ROOT / "data").resolve()
    store = Store(global_file or directory / "global_stats.json", log_config=log_config)

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            store.runtime_log.record(logging.INFO, "Aplicación detenida.", "shutdown")
            store.runtime_log.close()

    app = FastAPI(title="Order Manager", version="0.3.1", lifespan=lifespan)
    notices = OperationNotices()
    app.state.operation_notices = notices
    app.add_middleware(NoticeContext, notices=notices)
    app.add_middleware(RequestDiagnostics, runtime=store.runtime_log)
    app.add_middleware(LocalSecurity, token=token_urlsafe(32), runtime=store.runtime_log,
                       allowed_hosts=allowed_hosts)
    app.state.store = store
    navigation = JourneyNavigation()
    app.state.journey_navigation = navigation
    health = HealthCheck(store)
    app.state.health = health

    @app.get("/api/health")
    def health_status():
        result = health.check()
        return JSONResponse(result, status_code=503 if result["status"] == "unavailable" else 200)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        details = [{"loc": list(item["loc"]), "msg": item["msg"], "type": item["type"]}
                   for item in error.errors()]
        return JSONResponse({"detail": details}, status_code=422)

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, error: DomainError):
        if not request.url.path.startswith("/api/"):
            title = "Almacenamiento no disponible" if error.status == 503 else "Acción no disponible"
            return HTMLResponse(web.layout(title, web.alert(str(error)), show_notice=False),
                                status_code=error.status)
        return JSONResponse({"detail": str(error)}, status_code=error.status)

    @app.get("/api/storage")
    def storage_status():
        return {"available": not store.storage.blocked, "warnings": store.storage.warnings,
                "revision": store.storage.revision, "diagnostic_log_available": not store.runtime_log.file.failed}

    @app.get("/api/journey/recovery")
    def recovery_info():
        return store.recovery_info()

    @app.post("/api/journey/recover")
    def recover_journey(data: RecoveryConfirmation):
        return store.recover_journey(data.close_id, data.revision, data.active_id)

    @app.get("/api/journey")
    def get_journey():
        return store.get_journey()

    @app.post("/api/journey", status_code=201)
    def create_journey(data: JourneyInput):
        return store.create_journey(data.title)

    @app.patch("/api/journey")
    def rename_journey(data: JourneyInput):
        return store.rename_journey(data.title)

    @app.post("/api/journey/close")
    def close_journey(data: JourneyConfirmation):
        payload = store.close_journey(data.journey_id)
        return Response(
            payload,
            media_type="application/json",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="jornada-{data.journey_id}.json"'
                )
            },
        )

    @app.get("/api/exports/last")
    def latest_export(journey_id: str | None = None, format: ExportFormat = "json",
                      close_id: str | None = None):
        journey_id, payload = store.get_last_export(journey_id, close_id)
        try:
            filename, media_type, content = download_file(journey_id, payload, format)
        except Exception as error:
            store.runtime_log.record(logging.ERROR, "Falló la generación de la descarga.", "export_failed",
                                    error=error, journey_id=journey_id, format=format)
            raise
        store.runtime_log.record(logging.INFO, "Descarga generada.", "export_generated", journey_id=journey_id, format=format)
        return Response(
            content,
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            },
        )

    @app.post("/api/journey/discard", status_code=204)
    def discard_journey(data: JourneyConfirmation):
        store.discard_journey(data.journey_id)
        return Response(status_code=204)

    @app.get("/api/authors")
    def authors():
        return (store.get_journey() or {}).get("authors", [])

    @app.post("/api/authors", status_code=201)
    def add_author(data: NameInput):
        return store.add_author(data.name)

    @app.patch("/api/authors/{author_id}")
    def rename_author(author_id: str, data: NameInput):
        return store.rename_author(author_id, data.name)

    @app.delete("/api/authors/{author_id}", status_code=204)
    def delete_author(author_id: str):
        store.delete_author(author_id)
        return Response(status_code=204)

    @app.get("/api/articles")
    def articles():
        return store.get_available_articles() if store.get_journey() else []

    @app.get("/api/inventory")
    def inventory():
        return store.get_inventory()

    @app.post("/api/articles", status_code=201)
    def add_article(data: ArticleInput):
        return store.add_article(data.model_dump())

    @app.put("/api/articles/{article_id}")
    def update_article(article_id: str, data: ArticleInput):
        return store.update_article(article_id, data.model_dump())

    @app.delete("/api/articles/{article_id}", status_code=204)
    def delete_article(article_id: str):
        store.delete_article(article_id)
        return Response(status_code=204)

    @app.get("/api/orders")
    def orders():
        return (store.get_journey() or {}).get("orders", [])

    @app.post("/api/orders", status_code=201)
    def create_order(data: OrderInput):
        return store.save_order(
            data.author_id, [line.model_dump() for line in data.lines], status=data.status,
            series=data.series, serial_number=data.serial_number, batch_id=data.batch_id,
        )

    @app.put("/api/orders/{order_id}")
    def update_order(order_id: str, data: OrderInput):
        lines = [line.model_dump() for line in data.lines]
        return store.save_order(data.author_id, lines, order_id, status=data.status,
                                series=data.series, serial_number=data.serial_number, batch_id=data.batch_id)

    @app.delete("/api/orders/{order_id}", status_code=204)
    def delete_order(order_id: str):
        store.delete_order(order_id)
        return Response(status_code=204)

    @app.get("/api/statistics/journey")
    def journey_statistics():
        return store.get_summary()

    @app.get("/api/statistics/global")
    def global_statistics():
        return store.get_globals()

    @app.get("/api/events")
    def events():
        return store.get_events()

    @app.get("/static/styles.css")
    def css():
        return FileResponse(ROOT / "static" / "styles.css", media_type="text/css")

    @app.get("/", response_class=HTMLResponse)
    def dashboard():
        return web.dashboard(store)

    @app.get("/jornada", response_class=HTMLResponse)
    def journey_page(request: Request):
        values = dict(request.query_params)
        warning = ""
        if "pages" in values:
            journey = store.get_journey()
            saved = navigation.load(values["pages"], journey["id"] if journey else "")
            if saved is None:
                values = {}
                warning = "El enlace de navegación caducó o pertenece a otra jornada. Las tablas vuelven a la primera página."
            else:
                values = {**saved, **values}
        return web.journey_page(
            store, error=warning, navigation=navigation,
            batch_page=values.get("batch_page", "1"),
            article_pages=web.journey_article_pages(values),
            order_pages=journey_results.page_values(values, "orders"),
            subtotal_pages=journey_results.page_values(values, "subtotals"),
        )

    @app.get("/ordenes", response_class=HTMLResponse)
    def orders_page(
        edit: str = "", article: str = "", page: int = Query(default=1, ge=1), q: str = "",
        search_by: str = "all",
    ):
        if edit:
            return RedirectResponse(web.order_editor_url(edit, page, article, q, search_by), status_code=303)
        return web.orders_page(store, article_id=article, page=page, query=q, search_by=search_by)

    @app.get("/articulos", response_class=HTMLResponse)
    def articles_page(
        edit: str = "", q: str = "", category: str = "", subcategory: str = "",
        page: int = Query(default=1, ge=1), sold_page: int = Query(default=1, ge=1),
    ):
        search = ArticleSearch(q, category, subcategory, page, sold_page)
        return web.articles_page(store, edit_id=edit, search=search)

    @app.get("/registros", response_class=HTMLResponse)
    def events_page(page: int = Query(default=1, ge=1)):
        return web.events_page(store, page=page)

    @app.get("/exportaciones", response_class=HTMLResponse)
    def exports_page(journey_id: str, close_id: str | None = None):
        try:
            store.get_last_export(journey_id, close_id)
        except DomainError as error:
            return HTMLResponse(web.layout("Exportación no disponible", (
                f'<p role="alert">{web.h(error)}</p>'
                '<a class="button quiet" href="/">Volver al Dashboard</a>'
            ), show_notice=False), status_code=error.status)
        return web.closed_journey_page(journey_id, store._export_close_id)

    @app.get("/confirmar/{action}", response_class=HTMLResponse)
    def confirm_page(action: str):
        return web.confirm_page(store, action)

    async def fields(request: Request) -> dict[str, str]:
        raw = await request.body()
        if len(raw) > 65536:
            raise DomainError("Formulario demasiado grande.", 413)
        parsed = parse_qs(raw.decode("utf-8"), keep_blank_values=True,
                          max_num_fields=MAX_FIELDS, errors="strict")
        for key in ("q", "filter_category", "filter_subcategory"):
            try:
                bounded_text(parsed.get(key, [""])[-1], "Filtro")
            except ValueError as error:
                raise DomainError(str(error)) from None
        return {key: values[-1] for key, values in parsed.items()}

    @app.post("/ui/journey")
    async def journey_action(request: Request):
        values = await fields(request)
        try:
            action = values.get("action")
            details = {}
            if action == "create":
                store.create_journey(values.get("title", ""))
            elif action == "rename":
                store.rename_journey(values.get("title", ""), values.get("journey_id", ""))
            elif action == "add_author":
                with store.lock:
                    author = store.add_author(values.get("name", ""))
                    details = {"author": author["name"], "journey": store.get_journey()["title"]}
            elif action == "rename_author":
                store.rename_author(
                    values.get("author_id", ""),
                    values.get("name", ""),
                )
            elif action == "delete_author":
                store.delete_author(values.get("author_id", ""))
            elif action == "close" and values.get("confirm") == "yes":
                journey_id = values.get("journey_id", "")
                store.close_journey(journey_id)
                target = "/exportaciones?" + urlencode({
                    "journey_id": journey_id, "close_id": store._export_close_id,
                })
                return RedirectResponse(notices.url(target, "journey_closed"), status_code=303)
            elif action == "recover" and values.get("confirm") == "yes":
                recovered = store.recover_journey(
                    values.get("close_id", ""), values.get("revision", ""), values.get("active_id", ""),
                )
                details = {"journey": recovered["title"]}
            elif action == "discard" and values.get("confirm") == "yes":
                store.discard_journey(values.get("journey_id", ""))
            else:
                raise DomainError("Acción no reconocida.")
            code = {"create": "journey_created", "rename": "journey_updated",
                    "add_author": "author_created", "rename_author": "author_updated",
                    "delete_author": "author_deleted", "recover": "journey_recovered",
                    "discard": "journey_discarded"}[action]
            return RedirectResponse(notices.url("/jornada", code, **details), status_code=303)
        except DomainError as error:
            rename_title = values.get("title", "") if values.get("action") == "rename" else None
            return HTMLResponse(
                web.journey_page(
                    store, str(error), rename_title=rename_title, author_values=values,
                ),
                status_code=error.status,
            )

    @app.post("/ui/articles")
    async def article_action(request: Request):
        values = await fields(request)
        search = ArticleSearch.from_form(values)
        try:
            details = {}
            if values.get("action") == "delete":
                store.delete_article(values.get("article_id", ""))
            else:
                data = {
                    key: values.get(key, "")
                    for key in ("name", "category", "subcategory", "unit_price")
                }
                inventory = store.get_inventory()
                data["category"] = values.get("category_article", data["category"])
                values["category"] = data["category"]
                category = next(
                    (item for item in inventory["categories"] if item["name"] == data["category"]),
                    None,
                )
                if category is None:
                    raise DomainError("Selecciona una categoría existente.")
                position = inventory["categories"].index(category)
                data["subcategory"] = values.get(
                    f"subcategory_article_{position}", data["subcategory"],
                )
                values.update(category=data["category"], subcategory=data["subcategory"])
                values["subcategories"] = {
                    str(index): values.get(f"subcategory_article_{index}", "")
                    for index in range(len(inventory["categories"]))
                }
                if not any(
                    item["category_id"] == category["id"] and item["name"] == data["subcategory"]
                    for item in inventory["subcategories"]
                ):
                    raise DomainError("Selecciona una subcategoría de esa categoría.")
                if values.get("article_id"):
                    article = store.update_article(values["article_id"], data)
                    details = {"article": article["name"]}
                else:
                    store.add_article(data)
            code = ("article_deleted" if values.get("action") == "delete" else
                    "article_updated" if values.get("article_id") else "article_created")
            target = search.url() + "#article-results"
            return RedirectResponse(notices.url(target, code, **details), status_code=303)
        except DomainError as error:
            return HTMLResponse(
                web.articles_page(
                    store,
                    edit_id=values.get("article_id", ""),
                    error=str(error),
                    values=values if values.get("action") != "delete" else None,
                    search=search,
                ),
                status_code=error.status,
            )

    def order_list_state(values: dict) -> dict:
        try:
            page = max(1, int(values.get("page", "1")))
        except ValueError:
            page = 1
        return {
            "page": page, "article_id": values.get("article", ""),
            "query": values.get("q", ""), "search_by": values.get("search_by", "all"),
        }

    @app.post("/ui/orders/delete")
    async def order_delete(request: Request):
        values = await fields(request)
        state = order_list_state(values)
        try:
            with store.lock:
                journey = store.get_journey() or {"orders": [], "authors": []}
                order = next((item for item in journey["orders"]
                              if item["id"] == values.get("order_id", "")), None)
                store.delete_order(values.get("order_id", ""))
                details = order_details(order, journey)
            target = web.orders_url(**state) + "#order-results"
            return RedirectResponse(notices.url(target, "order_deleted", **details), status_code=303)
        except DomainError as error:
            return HTMLResponse(
                web.orders_page(store, error=str(error), **state),
                status_code=error.status,
            )

    register_batch_ui(app, store, fields, notices)
    register_order_editor(app, store, fields, notices)
    return app


app = make_app()
