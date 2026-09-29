"""La vista de Artículos refleja las ventas actuales de la jornada."""

from order_manager.store import Store
from order_manager.web import articles_page


def test_sold_catalog_counts_units_and_tracks_order_changes(tmp_path):
    store = Store(tmp_path / "globals.json")
    store.create_journey("Turno")
    author = store.add_author("Ana")
    store.add_article({
        "name": "Agua",
        "category": "Bebidas",
        "subcategory": "Aguas",
        "unit_price": 100,
    })

    def line(name, quantity):
        return {
            "name": name,
            "category": "Bebidas",
            "subcategory": "Aguas",
            "unit_price": 100,
            "quantity": quantity,
        }

    order = store.save_order(author["id"], [line("Café", 2), line("Té", 1)])
    store.save_order(author["id"], [line("Té", 2)])

    page = articles_page(store)
    sold = page.split("<h2>Catálogo vendido de la jornada</h2>", 1)[1].split(
        "<h2>Artículos disponibles para órdenes</h2>", 1
    )[0]
    assert sold.index("Bebidas / Aguas / Té") < sold.index("Bebidas / Aguas / Café")
    assert "<td>3</td>" in sold
    assert "Bebidas / Aguas / Agua</td>" not in sold
    assert "Agua" in page.split("<h2>Artículos disponibles para órdenes</h2>", 1)[1]

    store.save_order(author["id"], [line("Café", 4)], order["id"])
    updated = articles_page(store)
    sold_updated = updated.split("<h2>Catálogo vendido de la jornada</h2>", 1)[1].split(
        "<h2>Artículos disponibles para órdenes</h2>", 1
    )[0]
    assert sold_updated.index("Bebidas / Aguas / Café") < sold_updated.index(
        "Bebidas / Aguas / Té"
    )

    store.delete_order(order["id"])
    after_delete = articles_page(store)
    sold_after_delete = after_delete.split(
        "<h2>Catálogo vendido de la jornada</h2>", 1
    )[1].split("<h2>Artículos disponibles para órdenes</h2>", 1)[0]
    assert "Bebidas / Aguas / Café" not in sold_after_delete
    assert "Bebidas / Aguas / Té" in sold_after_delete
