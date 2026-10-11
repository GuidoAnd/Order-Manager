"""Límites compartidos para entradas nuevas, sin modificar datos históricos."""

import unicodedata


MAX_TEXT = 200
MAX_TAXONOMY = 120


def bounded_text(value: str, label: str, maximum: int = MAX_TEXT) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label}: debe ser texto.")
    if len(value) > maximum:
        raise ValueError(f"{label}: máximo {maximum} caracteres.")
    if any(unicodedata.category(char) == "Cc" for char in value):
        raise ValueError(f"{label}: contiene caracteres de control no permitidos.")
    return value.strip()
