"""Recuperación persistente, atomicidad y rollback de jornadas."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from order_manager import persistence
from order_manager.api import make_app
from order_manager.seed_inventory import initial_inventory
from order_manager.store import DomainError, Store, fresh_globals
from test_review_fixes import request


def active(tmp_path):
    store = Store(tmp_path / "global_stats.json")
    store.create_journey("Anterior")
    author = store.add_author("Ana")
    return store, author


def line(name="Nuevo", price=100):
    return {"name": name, "category": "Otros", "subcategory": "Otros",
            "unit_price": price, "quantity": 2}


def restore(store):
    return Store(store.data_dir / "global_stats.json")


def test_every_action_and_discard_survive_restart(tmp_path):
    store, author = active(tmp_path)
    order = store.save_order(author["id"], [line()])
    assert restore(store).get_journey() == store.get_journey()
    store.rename_author(author["id"], "Ana nueva")
    assert restore(store).get_journey() == store.get_journey()
    store.delete_order(order["id"])
    store.discard_journey()
    restored = restore(store)
    assert restored.get_journey() is None
    assert any(a["name"] == "Nuevo" for a in restored.get_inventory()["articles"])
    assert restored.get_events()[-1]["action"] == "journey_discarded"


def test_validation_does_not_leave_partial_catalog_or_revision(tmp_path):
    store, author = active(tmp_path)
    revision = store.storage.revision
    before = store.get_inventory()
    with pytest.raises(DomainError):
        store.save_order(author["id"], [line(), {**line("Inválido"), "quantity": 0}])
    assert store.get_inventory() == before
    assert store.storage.revision == revision
    assert restore(store).get_inventory() == before


def test_rollback_exact_state_keeps_newer_catalog_and_counts_reclose_once(tmp_path):
    store, author = active(tmp_path)
    order = store.save_order(author["id"], [line()])
    before = store.get_journey()
    payload = store.close_journey()
    assert restore(store).get_last_export()[1] == payload
    store.create_journey("Actual descartada")
    article = next(a for a in store.get_available_articles() if a["name"] == "Nuevo")
    store.update_article(article["id"], {**article, "unit_price": 300})
    store.add_article({k: v for k, v in line("Posterior").items() if k != "quantity"})
    store = restore(store)
    info = store.recovery_info()
    store.recover_journey(info["close_id"], info["revision"], info["active_id"])
    assert store.get_journey() == before
    assert store.get_globals()["journeys"] == 0
    assert next(a for a in store.get_available_articles() if a["name"] == "Nuevo")["unit_price"] == 300
    assert any(a["name"] == "Posterior" for a in store.get_available_articles())
    with pytest.raises(DomainError):
        store.get_last_export()
    with pytest.raises(DomainError):
        store.recover_journey(info["close_id"], info["revision"], info["active_id"])
    store.save_order(author["id"], [{**line(), "unit_price": 150}], order["id"])
    store.close_journey()
    assert restore(store).get_globals()["revenue"] == 300
    assert restore(store).get_globals()["journeys"] == 1
    events = [e["action"] for e in store.get_events()]
    assert events.count("journey_closed") == 2
    assert "journey_discarded_for_recovery" in events and "journey_recovered" in events


def test_edit_keeps_saved_price_and_allows_explicit_change(tmp_path):
    store, author = active(tmp_path)
    article = store.get_available_articles()[0]
    store.update_article(article["id"], {**article, "unit_price": 100})
    row = {"catalog_id": article["id"], "quantity": 2}
    order = store.save_order(author["id"], [row])
    store.update_article(article["id"], {**article, "unit_price": 300})
    assert store.save_order(author["id"], [row], order["id"])["total"] == 200
    assert store.save_order(author["id"], [{**row, "unit_price": 150}], order["id"])["total"] == 300
    assert store.save_order(author["id"], [row])["total"] == 600


@pytest.mark.parametrize("stage", ["component", "manifest"])
def test_failure_before_publication_keeps_last_action(tmp_path, stage):
    store, _ = active(tmp_path)
    before = store.get_journey()
    original = persistence.write_json
    def fail(path, value):
        if (stage == "component" and path.name == "journey.json") or (stage == "manifest" and path.name == "current.json"):
            raise OSError("disk full")
        original(path, value)
    with patch.object(persistence, "write_json", side_effect=fail):
        with pytest.raises(DomainError, match="guardado"):
            store.rename_journey("No confirmada")
    assert store.get_journey() == before
    assert restore(store).get_journey() == before
    assert not store.storage.blocked


def test_failure_after_replace_reconciles_without_duplicate_close(tmp_path):
    store, _ = active(tmp_path)
    original = persistence.write_json
    def fail_after(path, value):
        original(path, value)
        if path.name == "current.json":
            raise OSError("fsync interrupted")
    with patch.object(persistence, "write_json", side_effect=fail_after):
        store.close_journey()
    assert restore(store).get_globals()["journeys"] == 1
    assert store.get_journey() is None
    with pytest.raises(DomainError):
        store.close_journey()


def test_corruption_falls_back_and_invalid_copies_block_without_reset(tmp_path):
    store, _ = active(tmp_path)
    before = store.get_journey()
    store.rename_journey("Última")
    store.storage.component_path("journey").write_text("truncated")
    restored = restore(store)
    assert restored.get_journey() == before
    assert restored.storage.warnings
    assert list((tmp_path / "damaged").iterdir())
    restored.storage.component_path("inventory").write_text("truncated")
    broken = restore(store)
    assert broken.storage.blocked
    with pytest.raises(DomainError, match="recuperación"):
        broken.create_journey("No reiniciar datos")
    app = make_app(data_dir=tmp_path)
    status, _, body = request(app, "GET", "/jornada")
    assert status == 503 and "recuperación" in body
    assert request(app, "GET", "/api/storage")[0] == 200


def test_corrupt_rollback_does_not_lose_healthy_active_journey(tmp_path):
    store, _ = active(tmp_path)
    store.close_journey()
    store.create_journey("Sana")
    before = store.get_journey()
    store.storage.component_path("rollback").write_text("damaged")
    restored = restore(store)
    assert restored.get_journey() == before
    assert restored.recovery_info() is None
    restored.rename_journey("Todavía operativa")
    assert restore(store).get_journey()["title"] == "Todavía operativa"


def test_manifest_backup_and_unconfirmed_revision(tmp_path):
    store, _ = active(tmp_path)
    before = store.get_journey()
    store.rename_journey("Última")
    store.storage.directory.joinpath("current.json").write_text("bad")
    restored = restore(store)
    assert restored.get_journey() == before
    assert restored.storage.warnings
    orphan = tmp_path / "revisions" / ("a" * 32)
    orphan.mkdir(exist_ok=True)
    (orphan / "journey.json").write_text('{"title":"No confirmada"}')
    assert restore(restored).get_journey() == before


def test_migration_keeps_originals_and_rejects_broken_inventory(tmp_path):
    inventory = tmp_path / "inventory.json"
    globals_file = tmp_path / "global_stats.json"
    inventory.write_text(json.dumps(initial_inventory()))
    globals_file.write_text(json.dumps(fresh_globals()))
    originals = (inventory.read_bytes(), globals_file.read_bytes())
    store = Store(globals_file)
    assert not store.storage.blocked
    store.create_journey("Nueva")
    assert (inventory.read_bytes(), globals_file.read_bytes()) == originals
    invalid = tmp_path / "invalid"
    invalid.mkdir()
    (invalid / "inventory.json").write_text("bad")
    broken = Store(invalid / "global_stats.json")
    assert broken.storage.blocked and not (invalid / "current.json").exists()


def test_data_dir_configuration_and_stale_recovery(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = make_app()
    store = app.state.store
    assert store.data_dir == tmp_path
    store.create_journey("Anterior")
    store.close_journey()
    info = store.recovery_info()
    store.create_journey("Actual")
    status, _, _ = request(app, "POST", "/api/journey/recover", info)
    assert status == 409 and store.get_journey()["title"] == "Actual"


def test_history_write_failure_retries_after_restart(tmp_path):
    store, _ = active(tmp_path)
    original = persistence.write_json
    def fail(path, value):
        if "actions" in path.parts:
            raise OSError("logs unavailable")
        original(path, value)
    with patch.object(persistence, "write_json", side_effect=fail):
        store.close_journey()
    restored = restore(store)
    events = restored.get_events()
    assert sum(e["action"] == "journey_closed" for e in events) == 1
    assert restored.get_globals()["journeys"] == 1


def test_unsupported_schema_is_preserved_and_blocks_operations(tmp_path):
    store, _ = active(tmp_path)
    path = tmp_path / "current.json"
    manifest = json.loads(path.read_text())
    manifest["schema"] = 99
    path.write_text(json.dumps(manifest))
    original = path.read_bytes()
    restored = restore(store)
    assert restored.storage.blocked
    assert path.read_bytes() == original


def test_permanent_sync_failure_after_publication_requires_restart(tmp_path):
    store, _ = active(tmp_path)
    original = persistence.sync_directory
    published = False
    original_replace = persistence.os.replace
    def replace(source, destination):
        nonlocal published
        original_replace(source, destination)
        if Path(destination).name == "current.json":
            published = True
    def sync(path):
        if path == tmp_path and published:
            raise OSError("durability unknown")
        original(path)
    with patch.object(persistence.os, "replace", side_effect=replace), patch.object(persistence, "sync_directory", side_effect=sync):
        with pytest.raises(DomainError, match="guardado"):
            store.close_journey()
    assert store.storage.blocked
    restored = restore(store)
    assert restored.get_journey() is None and restored.get_globals()["journeys"] == 1


def test_close_write_failure_preserves_active_journey_and_snapshot(tmp_path):
    store, _ = active(tmp_path)
    store.close_journey()
    store.create_journey("Actual")
    before = deepcopy(store._state())
    info = store.recovery_info()
    with patch.object(store.storage, "commit", side_effect=OSError("permission denied")):
        with pytest.raises(DomainError):
            store.recover_journey(info["close_id"], info["revision"], info["active_id"])
    assert store._state() == before
    assert restore(store).get_journey() == store.get_journey()


def test_revision_retention_is_bounded_and_preserves_latest_snapshot(tmp_path):
    store, _ = active(tmp_path)
    store.close_journey()
    close_id = store.recovery_info()["close_id"]
    store.create_journey("Actual")
    for number in range(8):
        store.rename_journey(f"Actual {number}")
    assert len(list((tmp_path / "revisions").iterdir())) == 2
    assert restore(store).recovery_info()["close_id"] == close_id


def test_old_download_selector_rejects_reclosed_journey(tmp_path):
    app = make_app(data_dir=tmp_path)
    store = app.state.store
    store.create_journey("Misma jornada")
    store.close_journey()
    info = store.recovery_info()
    jid = info["journey_id"]
    close_id = info["close_id"]
    store.recover_journey(close_id, info["revision"], info["active_id"])
    store.close_journey()
    assert request(app, "GET", f"/api/exports/last?journey_id={jid}&close_id={close_id}")[0] == 404
    assert request(app, "GET", f"/exportaciones?journey_id={jid}&close_id={close_id}")[0] == 404
    assert request(app, "GET", f"/api/exports/last?journey_id={jid}")[0] == 200


def test_cleanup_failure_does_not_undo_confirmed_action(tmp_path):
    store, _ = active(tmp_path)
    with patch.object(store.storage, "prune", side_effect=OSError("permission denied")):
        store.rename_journey("Confirmada")
    assert store.get_journey()["title"] == "Confirmada"
    assert restore(store).get_journey()["title"] == "Confirmada"


def test_edit_saved_line_after_catalog_article_was_deleted(tmp_path):
    store, author = active(tmp_path)
    article = next(a for a in store.get_available_articles() if a["unit_price"] is not None)
    row = {"catalog_id": article["id"], "quantity": 2}
    order = store.save_order(author["id"], [row])
    store.delete_article(article["id"])
    edited = store.save_order(author["id"], [{**row, "quantity": 3}], order["id"])
    assert edited["total"] == 3 * article["unit_price"]
    assert not any(a["id"] == article["id"] or a["name"] == article["name"] for a in store.get_inventory()["articles"])
    with pytest.raises(DomainError):
        store.save_order(author["id"], [row])


def test_corrupt_manifest_cannot_resolve_arbitrary_paths(tmp_path):
    store, _ = active(tmp_path)
    manifest_path = tmp_path / "current.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["current"]["id"] = "../../outside"
    manifest_path.write_text(json.dumps(manifest))
    restored = restore(store)
    assert not restored.storage.blocked
    assert restored.storage.warnings
    assert restored.get_journey()["title"] == "Anterior"
