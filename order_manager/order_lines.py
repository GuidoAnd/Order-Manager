"""Identidad estable de líneas nuevas y de órdenes anteriores sin identificador."""

from uuid import NAMESPACE_URL, uuid5


def line_identifier(order_id: str, index: int, line: dict) -> str:
    return line.get("line_id") or str(uuid5(NAMESPACE_URL, f"order-manager:line:{order_id}:{index}"))
