"""Formato de descarga de una jornada, separado del inventario de trabajo."""

from copy import deepcopy


def build_export(
    journey: dict, statistics: dict, new_articles: list[dict],
    price_changes: list[dict], closed_at: str,
) -> dict:
    result = deepcopy({
        key: journey[key]
        for key in ("id", "title", "opened_at", "authors", "orders", "events")
    })
    result.update({
        "export_format": "v0.2",
        "closed_at": closed_at,
        "new_articles": deepcopy(new_articles),
        "price_changes": deepcopy(price_changes),
        "statistics": deepcopy(statistics),
    })
    result["events"].append({
        "at": closed_at, "action": "journey_closed", "detail": journey["title"],
    })
    return result
