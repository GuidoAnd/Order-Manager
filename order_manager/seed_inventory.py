"""Catálogo inicial de v0.2; los cambios posteriores viven en data/inventory.json."""

from __future__ import annotations


CATEGORIES = (
    ("1", "Bebidas con alcohol"),
    ("2", "Bebidas sin alcohol"),
    ("3", "Comida"),
    ("4", "Cafetería"),
    ("5", "Postres"),
    ("6", "Otros"),
    ("7", "Promociones"),
)

SUBCATEGORIES = (
    ("vt", "Vinos tintos", "1"),
    ("vb", "Vinos blancos secos", "1"),
    ("vd", "Vinos dulces", "1"),
    ("ch", "Champaña", "1"),
    ("sd", "Sidras", "1"),
    ("ap", "Aperitivos", "1"),
    ("ah", "Aperitivos sin alcohol", "2"),
    ("mn", "Minutas", "3"),
    ("mf", "Minutas frías", "3"),
    ("pr", "Preparados", "3"),
    ("pe", "Platos especiales", "3"),
    ("pd", "Platos del día", "3"),
    ("if", "Infusiones", "4"),
    ("dc", "Dulces comestibles", "5"),
    ("gl", "Golosinas", "5"),
    ("ot", "Otros", "6"),
    ("gs", "Gaseosas", "2"),
    ("am", "Aguas minerales", "2"),
    ("as", "Aguas saborizadas", "2"),
    ("lc", "Latas de cerveza", "1"),
    ("pm", "Promociones", "7"),
)

# Nombre, código de subcategoría, precio unitario. None pide precio en la orden.
PRODUCTS = (
    ("Agua Villamanaos 600cc", "am", None),
    ("Agua con gas ECO 500cc", "am", None),
    ("Saborizada de pomelo Levite", "as", None),
    ("Saborizada de manzana Levite", "as", None),
    ("Coca-cola 600cc", "gs", None),
    ("Coca-cola zero 600cc", "gs", None),
    ("Sprite 600cc", "gs", None),
    ("7_UP 500cc", "gs", None),
    ("Tonica Cunnington 500cc", "gs", None),
    ("Brahama 473cc", "lc", None),
    ("Quilmes 473cc", "lc", None),
    ("Quilmes stout 473cc", "lc", None),
    ("Stella 473cc", "lc", None),
    ("Speed 250cc", "ah", None),
    ("Medida de fernet", "ap", None),
    ("Medida de Gancia", "ap", None),
    ("Medida de otro", "ap", None),
    ("Gancia batido", "ap", None),
    ("Fernet cola", "ap", None),
    ("Ron cola", "ap", None),
    ("GinTonic", "ap", None),
    ("Medida de whisky", "ap", None),
    ("Whiscola", "ap", None),
    ("Garibaldi", "ap", None),
    ("Dr Lemon 1lt", "ap", None),
    ("Federico de alvear extra dulce", "ch", None),
    ("Federico de alvear extra brut", "ch", None),
    ("Chandom Delice", "ch", None),
    ("Del Valle 750cc", "sd", None),
    ("Quara", "vt", None),
    ("Alma mora", "vt", None),
    ("Santa julia malbec", "vt", None),
    ("Santa julia seco", "vb", None),
    ("otros vinos blancos", "vb", None),
    ("Santa Julia chenin", "vd", None),
    ("Cosecha tardia Norton", "vd", None),
    ("Copa de vino", "vt", None),
    ("Sandwich de miga triple x2", "mf", None),
    ("Sandwiches tostados x2", "mn", None),
    ("Sandwiches tostados x4", "mn", 8800),
    ("Empanadas de carne", "mn", 2800),
    ("Empanadas de jyq", "mn", 2800),
    ("Empanadas de pollo", "mn", 2800),
    ("Pizza muzzarella", "mn", 15000),
    ("Pizza especial", "mn", 17000),
    ("Pizza porcion muzzarella", "mn", 2800),
    ("Pizza porcion especial", "mn", 2800),
    ("Picada para 4", "mf", 29000),
    ("Picada para 2", "mf", 18000),
    ("Picada individual", "mf", 12000),
    ("Platito de fiambres y queso", "mf", 8000),
    ("Snack", "mf", 5000),
    ("Hamburguesa", "pr", 9000),
    ("Porcion de fritas", "mn", 7000),
    ("Milanesa c/guarnicion", "pr", 15000),
    ("Milanesa Napolitana c/guarnicion", "pr", 16500),
    ("Rodaja de Limon", "ot", 1400),
    ("huevo frito", "pr", 2000),
    ("Porcion de tarta", "dc", 4800),
    ("Helado", "dc", 5500),
    ("Cafe", "if", 2800),
    ("Cafe cortado", "if", 2800),
    ("Cafe lagrima", "if", 2800),
    ("Te", "if", 2800),
    ("Alfajores", "gl", None),
    ("Pastillas", "gl", None),
    ("Chicles Alfajores", "gl", None),
    ("Dulces integrales", "dc", None),
)


def initial_inventory() -> dict:
    categories = [
        {"id": category_id, "name": name}
        for category_id, name in CATEGORIES
    ]
    subcategories = [
        {"id": code, "name": name, "category_id": category_id}
        for code, name, category_id in SUBCATEGORIES
    ]
    category_names = {category["id"]: category["name"] for category in categories}
    subcategory_names = {
        item["id"]: item for item in subcategories
    }
    articles = []
    for index, (name, code, price) in enumerate(PRODUCTS, start=1):
        subcategory = subcategory_names[code]
        articles.append({
            "id": f"seed-{index:03d}",
            "name": name,
            "category": category_names[subcategory["category_id"]],
            "subcategory": subcategory["name"],
            "unit_price": price,
        })
    return {
        "categories": categories,
        "subcategories": subcategories,
        "articles": articles,
    }
