"""Punto de entrada ASGI para herramientas que buscan api.py en la raíz."""

from order_manager.api import app

__all__ = ["app"]
