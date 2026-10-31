"""Series fijas y numeración manual, independientes del contador cronológico."""


SERIES_RANGES = {"10": (1, 80), "20": (81, 160)}


def validate_serial(series: str, number: object) -> tuple[str, int]:
    if not isinstance(series, str) or series not in SERIES_RANGES:
        raise ValueError("Serie: seleccione 10 o 20.")
    if isinstance(number, bool) or not str(number).isdecimal():
        raise ValueError("Numeración: ingrese un número entero del rango elegido.")
    digits = str(number).lstrip("0") or "0"
    if len(digits) > 3:
        raise ValueError("Numeración: fuera del rango de la serie elegida.")
    value = int(digits)
    minimum, maximum = SERIES_RANGES[series]
    if not minimum <= value <= maximum:
        raise ValueError(f"Numeración: la serie {series} admite {minimum:03d}–{maximum:03d}.")
    return series, value


def serial_label(order: dict) -> str:
    if order.get("series") is None:
        return ""
    return f"Serie {order['series']} · {order['serial_number']:03d}"


def legacy_series(number: object) -> str:
    """Permite corregir órdenes anteriores que todavía no tenían serie ni tanda."""
    if isinstance(number, bool) or not str(number).isascii() or not str(number).isdecimal():
        raise ValueError("Numeración: ingrese un entero entre 001 y 160.")
    digits = str(number).lstrip("0") or "0"
    if len(digits) > 3 or not 1 <= int(digits) <= 160:
        raise ValueError("Numeración: ingrese un entero entre 001 y 160.")
    return "10" if int(digits) <= 80 else "20"
