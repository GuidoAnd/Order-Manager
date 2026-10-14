"""Validación de documentos persistentes; no depende del estado en memoria."""

from .order_series import validate_serial


def require(condition: bool) -> None:
    if not condition:
        raise ValueError("Estado persistente inválido.")


def natural(value: object, minimum: int = 0) -> bool:
    return type(value) is int and value >= minimum


def text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def unique(items: list) -> set:
    require(isinstance(items, list))
    ids = [item["id"] for item in items]
    require(all(text(value) for value in ids) and len(set(ids)) == len(ids))
    return set(ids)


def article(item: dict) -> None:
    require(all(text(item[key]) for key in ("name", "category", "subcategory")))
    require(item["unit_price"] is None or (natural(item["unit_price"]) and item["unit_price"] <= 2**63 - 1))


def inventory(data: dict) -> None:
    categories = unique(data["categories"])
    unique(data["subcategories"])
    unique(data["articles"])
    require(all(text(c["name"]) for c in data["categories"]))
    require(all(text(s["name"]) and s["category_id"] in categories
                for s in data["subcategories"]))
    names = {c["id"]: c["name"] for c in data["categories"]}
    taxonomy = {(names[s["category_id"]], s["name"]) for s in data["subcategories"]}
    for item in data["articles"]:
        article(item)
        require((item["category"], item["subcategory"]) in taxonomy)


def globals_data(data: dict) -> None:
    require(all(natural(data[k]) for k in ("journeys", "orders", "units", "revenue")))
    ids = data["closed_ids"]
    require(isinstance(ids, list) and len(set(ids)) == len(ids))
    require(all(text(value) for value in ids) and data["journeys"] == len(ids))
    for group in ("by_category", "by_article"):
        require(isinstance(data[group], dict))
        for value in data[group].values():
            require(natural(value["units"]) and natural(value["revenue"]))
        require(sum(v["units"] for v in data[group].values()) == data["units"])
        require(sum(v["revenue"] for v in data[group].values()) == data["revenue"])


def journey(data: dict | None) -> None:
    if data is None:
        return
    require(text(data["id"]) and text(data["title"]) and text(data["opened_at"]))
    authors = unique(data["authors"])
    require(all(text(a["name"]) for a in data["authors"]))
    require(len({a["name"].casefold() for a in data["authors"]}) == len(authors))
    unique(data["articles"])
    for item in data["articles"]:
        article(item)
    unique(data["orders"])
    numbers = []
    for order in data["orders"]:
        require(order["author_id"] in authors and natural(order["number"], 1))
        numbers.append(order["number"])
        if "series" in order or "serial_number" in order:
            require(isinstance(order.get("series"), str))
            require(type(order.get("serial_number")) is int)
            validate_serial(order["series"], order["serial_number"])
        require(order["status"] in {"sale", "not_billed"})
        require(isinstance(order["lines"], list) and 1 <= len(order["lines"]) <= 50)
        billed = order["status"] == "sale"
        for line in order["lines"]:
            article(line)
            require(natural(line["quantity"], 1) and line["quantity"] <= 2**63 - 1)
            if billed:
                require(natural(line["unit_price"]))
                require(natural(line["subtotal"]) and line["subtotal"] == line["quantity"] * line["unit_price"])
            else:
                require(line["unit_price"] is None and line["subtotal"] is None)
        require((natural(order["total"]) if billed else order["total"] is None))
        require(order["total"] == (sum(l["subtotal"] for l in order["lines"]) if billed else None))
    require(len(set(numbers)) == len(numbers))
    require(natural(data["next_order"], 1) and data["next_order"] > max(numbers, default=0))
    require(isinstance(data["events"], list))
    for event in data["events"]:
        require(all(text(event[k]) for k in ("at", "action", "detail")))


def activity(data: dict) -> None:
    require(isinstance(data["new_articles"], dict))
    for item in data["new_articles"].values():
        article(item)
    require(isinstance(data["price_changes"], list))
    for change in data["price_changes"]:
        for key in ("previous_price", "new_price"):
            require(change[key] is None or natural(change[key]))
    require(isinstance(data["catalog_keys"], list))
    require(all(isinstance(k, list) and len(k) == 3 and all(text(v) for v in k)
                for k in data["catalog_keys"]))


def validate_state(state: dict) -> None:
    inventory(state["inventory"])
    globals_data(state["global_stats"])
    active = state["journey"]
    journey(active["data"])
    activity(active["activity"])
    if active["data"]:
        require(active["data"]["id"] not in state["global_stats"]["closed_ids"])
    rollback = state["rollback"]
    if rollback:
        require(text(rollback["close_id"]))
        journey(rollback["journey"]["data"])
        activity(rollback["journey"]["activity"])
        globals_data(rollback["globals_before"])
        jid = rollback["journey"]["data"]["id"]
        require(jid in state["global_stats"]["closed_ids"])
        require(jid not in rollback["globals_before"]["closed_ids"])
        require(state["global_stats"]["closed_ids"] == rollback["globals_before"]["closed_ids"] + [jid])
        require(state["global_stats"]["journeys"] == rollback["globals_before"]["journeys"] + 1)
        from .store import summary
        stats = summary(rollback["journey"]["data"])
        for metric in ("orders", "units", "revenue"):
            require(state["global_stats"][metric] == rollback["globals_before"][metric] + stats[metric])
        for group in ("by_category", "by_article"):
            keys = set(state["global_stats"][group]) | set(rollback["globals_before"][group]) | set(stats[group])
            for key in keys:
                for metric in ("units", "revenue"):
                    require(state["global_stats"][group].get(key, {}).get(metric, 0) ==
                            rollback["globals_before"][group].get(key, {}).get(metric, 0) +
                            stats[group].get(key, {}).get(metric, 0))
    export = state["last_export"]
    if export:
        require(text(export["close_id"]) and text(export["journey_id"]))
        document = export["document"]
        require(document["id"] == export["journey_id"])
        candidate = {**document, "articles": [],
                     "next_order": max((o["number"] for o in document["orders"]), default=0) + 1}
        journey(candidate)
        from .store import summary
        require(document["statistics"] == summary(candidate))
        require(export["journey_id"] in state["global_stats"]["closed_ids"])
        if rollback:
            require(export["close_id"] == rollback["close_id"])
            require(export["journey_id"] == rollback["journey"]["data"]["id"])
