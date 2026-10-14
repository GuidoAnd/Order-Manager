"""Renderizado HTML compartido; las plantillas no reciben el almacenamiento."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape


TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
ENVIRONMENT = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(("html",)),
    undefined=StrictUndefined,
    cache_size=128,
    auto_reload=True,
    keep_trailing_newline=True,
)


def render(template: str, **context) -> str:
    return ENVIRONMENT.get_template(template).render(**context)


def component(name: str, *args) -> str:
    macro = getattr(ENVIRONMENT.get_template("components.html").module, name)
    return str(macro(*args))
