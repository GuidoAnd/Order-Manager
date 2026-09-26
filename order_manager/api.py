"""API HTTP y rutas de interfaz del gestor de órdenes."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from pydantic import BaseModel, Field

from . import web
from .store import DomainError, Store

ROOT = Path(__file__).resolve().parent.parent


class NameInput(BaseModel):
    name: str = Field(min_length=1)


class JourneyInput(BaseModel):
    title: str = Field(min_length=1)


class ArticleInput(BaseModel):
    name: str
    category: str
    subcategory: str
    unit_price: int = Field(ge=0)


class LineInput(BaseModel):
    catalog_id: str | None = None
    name: str | None = None
    category: str | None = None
    subcategory: str | None = None
    unit_price: int | None = Field(default=None, ge=0)
    quantity: int = Field(ge=1)


class OrderInput(BaseModel):
    author_id: str
    lines: list[LineInput] = Field(min_length=1, max_length=50)


def make_app(global_file: Path | None = None) -> FastAPI:
    app = FastAPI(title="Order Manager", version="0.1")
    store = Store(global_file or ROOT / "data" / "global_stats.json")
    app.state.store = store

    @app.exception_handler(DomainError)
    async def domain_error(_request: Request, error: DomainError):
        return JSONResponse({"detail": str(error)}, status_code=error.status)

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
    def close_journey():
        journey = store.get_journey()
        payload = store.close_journey()
        return Response(
            payload,
            media_type="application/json",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="jornada-{journey["id"]}.json"'
                )
            },
        )

    @app.get("/api/exports/last")
    def latest_export():
        journey_id, payload = store.get_last_export()
        return Response(
            payload,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="jornada-{journey_id}.json"'
            },
        )

    @app.post("/api/journey/discard", status_code=204)
    def discard_journey():
        store.discard_journey()
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
        return (store.get_journey() or {}).get("articles", [])

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
        return store.save_order(data.author_id, [line.model_dump() for line in data.lines])

    @app.put("/api/orders/{order_id}")
    def update_order(order_id: str, data: OrderInput):
        lines = [line.model_dump() for line in data.lines]
        return store.save_order(data.author_id, lines, order_id)

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
    def journey_page():
        return web.journey_page(store)

    @app.get("/ordenes", response_class=HTMLResponse)
    def orders_page(edit: str = ""):
        return web.orders_page(store, edit_id=edit)

    @app.get("/articulos", response_class=HTMLResponse)
    def articles_page(edit: str = ""):
        return web.articles_page(store, edit_id=edit)

    @app.get("/registros", response_class=HTMLResponse)
    def events_page():
        return web.events_page(store)

    @app.get("/confirmar/{action}", response_class=HTMLResponse)
    def confirm_page(action: str):
        return web.confirm_page(store, action)

    async def fields(request: Request) -> dict[str, str]:
        raw = await request.body()
        if len(raw) > 65536:
            raise DomainError("Formulario demasiado grande.", 413)
        parsed = parse_qs(raw.decode("utf-8"), keep_blank_values=True)
        return {key: values[-1] for key, values in parsed.items()}

    @app.post("/ui/journey")
    async def journey_action(request: Request):
        values = await fields(request)
        try:
            action = values.get("action")
            if action == "create":
                store.create_journey(values.get("title", ""))
            elif action == "rename":
                store.rename_journey(values.get("title", ""))
            elif action == "add_author":
                store.add_author(values.get("name", ""))
            elif action == "rename_author":
                store.rename_author(
                    values.get("author_id", ""),
                    values.get("name", ""),
                )
            elif action == "delete_author":
                store.delete_author(values.get("author_id", ""))
            elif action == "close" and values.get("confirm") == "yes":
                store.close_journey()
                return HTMLResponse(web.closed_journey_page())
            elif action == "discard" and values.get("confirm") == "yes":
                store.discard_journey()
            else:
                raise DomainError("Acción no reconocida.")
            return RedirectResponse("/jornada", status_code=303)
        except DomainError as error:
            return HTMLResponse(web.journey_page(store, str(error)), status_code=error.status)

    @app.post("/ui/articles")
    async def article_action(request: Request):
        values = await fields(request)
        try:
            if values.get("action") == "delete":
                store.delete_article(values.get("article_id", ""))
            else:
                data = {
                    key: values.get(key, "")
                    for key in ("name", "category", "subcategory", "unit_price")
                }
                if values.get("article_id"):
                    store.update_article(values["article_id"], data)
                else:
                    store.add_article(data)
            return RedirectResponse("/articulos", status_code=303)
        except DomainError as error:
            return HTMLResponse(
                web.articles_page(store, error=str(error)),
                status_code=error.status,
            )

    @app.post("/ui/orders/delete")
    async def order_delete(request: Request):
        values = await fields(request)
        try:
            store.delete_order(values.get("order_id", ""))
            return RedirectResponse("/ordenes", status_code=303)
        except DomainError as error:
            return HTMLResponse(
                web.orders_page(store, error=str(error)),
                status_code=error.status,
            )

    @app.post("/ui/orders/form")
    async def order_form(request: Request):
        values = await fields(request)
        try:
            count = int(values.get("count", "1"))
            if count < 1 or count > 50:
                raise DomainError("Número de líneas inválido.")
            keys = (
                "catalog_id",
                "name",
                "category",
                "subcategory",
                "quantity",
                "unit_price",
            )
            rows = [
                {key: values.get(f"{key}_{index}", "") for key in keys}
                for index in range(count)
            ]
            action = values.get("action", "")
            if action == "add":
                if len(rows) == 50:
                    raise DomainError("La orden admite hasta 50 líneas.")
                rows.append({})
            elif action.startswith("remove_"):
                rows.pop(int(action.split("_", 1)[1]))
                if not rows:
                    rows = [{}]
            elif action == "save":
                store.save_order(
                    values.get("author_id", ""),
                    rows,
                    values.get("order_id") or None,
                )
                return RedirectResponse("/ordenes", status_code=303)
            else:
                raise DomainError("Acción no reconocida.")
            page = web.orders_page(
                store,
                rows,
                values.get("author_id", ""),
                values.get("order_id", ""),
            )
            return HTMLResponse(page)
        except (DomainError, ValueError, IndexError) as error:
            return HTMLResponse(web.orders_page(store, error=str(error)), status_code=400)

    return app


app = make_app()
