"""Logging persistente, troubleshooting, rotación y fallos sin pérdida de negocio."""
import asyncio
from copy import deepcopy
import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from order_manager import persistence
from order_manager.api import make_app
from order_manager.runtime_logging import LogConfig, RuntimeLog
from order_manager.store import DomainError, Store
from test_review_fixes import request


def records(directory):
    path = directory / "logs" / "application.log"
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_default_info_and_configurable_debug_context(tmp_path, monkeypatch):
    store = Store(tmp_path / "global_stats.json")
    journey = store.create_journey("Nombre privado")
    assert all(r["level"] != "DEBUG" for r in records(tmp_path))
    assert any(r["operation"] == "create_journey" and r.get("journey_id") == journey["id"]
               for r in records(tmp_path))
    store.runtime_log.close()
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("LOG_MAX_BYTES", "8192")
    monkeypatch.setenv("LOG_BACKUP_COUNT", "3")
    restored = Store(tmp_path / "global_stats.json")
    assert restored.runtime_log.config == LogConfig("DEBUG", 8192, 3)
    restored.rename_journey("Otro nombre privado")
    assert any(r["level"] == "DEBUG" and r.get("phase") == "published" for r in records(tmp_path))
    assert all(r["at"].endswith("+00:00") for r in records(tmp_path))
    assert restored.get_journey()["id"] == journey["id"]
    restored.runtime_log.close()


@pytest.mark.parametrize("values", [{"LOG_LEVEL": "VERBOSE"}, {"LOG_MAX_BYTES": "secret-invalid"},
                                   {"LOG_MAX_BYTES": "0"}, {"LOG_BACKUP_COUNT": "0"},
                                   {"LOG_BACKUP_COUNT": "101"}])
def test_invalid_configuration_fails_without_echoing_values(monkeypatch, values):
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ValueError) as error:
        LogConfig.from_environment()
    assert "secret-invalid" not in str(error.value)


def test_rotation_is_bounded_and_does_not_rotate_history(tmp_path):
    store = Store(tmp_path / "global_stats.json", log_config=LogConfig("DEBUG", 1024, 2))
    store.create_journey("Prueba")
    for i in range(12):
        store.rename_journey(f"Nombre {i}")
    history = deepcopy(store.get_events())
    store.runtime_log.close()
    files = list((tmp_path / "logs").glob("application.log*"))
    assert len(files) == 3
    assert all(p.stat().st_size <= 1024 for p in files)
    restored = Store(tmp_path / "global_stats.json", log_config=LogConfig("INFO", 1024, 2))
    assert restored.get_events() == history
    assert len(list((tmp_path / "logs" / "actions").glob("*.json"))) == len(history)
    restored.runtime_log.close()


def test_log_write_failure_continues_and_recovers(tmp_path, capsys):
    app = make_app(data_dir=tmp_path)
    store = app.state.store
    store.runtime_log.file.close()
    with patch.object(store.runtime_log.file, "_open", side_effect=OSError("secret-error-message")):
        journey = store.create_journey("Secret-title")
        assert not store.storage.blocked
        assert store.runtime_log.file.failed
        status, _, body = request(app, "GET", "/api/storage")
        assert status == 200 and not json.loads(body)["diagnostic_log_available"]
    store.add_author("Secret-author")
    assert not store.runtime_log.file.failed
    output = capsys.readouterr().err
    assert '"operation": "logging_failed"' in output
    assert '"operation": "logging_recovered"' in output
    assert all(secret not in output for secret in ("Secret-title", "Secret-author", "secret-error-message"))
    restored = Store(tmp_path / "global_stats.json")
    assert restored.get_journey()["id"] == journey["id"]
    assert len(restored.get_events()) == 2
    store.runtime_log.close()
    restored.runtime_log.close()


def test_unavailable_log_directory_does_not_block_startup(tmp_path, capsys):
    (tmp_path / "logs").write_text("obstáculo")
    store = Store(tmp_path / "global_stats.json")
    assert not store.storage.blocked
    journey = store.create_journey("Abierta")
    assert store.runtime_log.file.failed
    assert store.get_events()[0]["journey_id"] == journey["id"]
    assert len(store._operation["pending_events"]) == 1
    assert "logging_failed" in capsys.readouterr().err
    store.runtime_log.close()


def test_pending_history_retries_after_restart_without_duplicate(tmp_path):
    store = Store(tmp_path / "global_stats.json")
    original = persistence.write_json

    def fail_history(path, value):
        if path.parent.name == "actions":
            raise OSError("secret-history-error")
        return original(path, value)

    with patch.object(persistence, "write_json", side_effect=fail_history):
        journey = store.create_journey("Privada")
        assert store.get_events()[0]["action"] == "journey_created"
    store.runtime_log.close()
    restored = Store(tmp_path / "global_stats.json")
    assert restored.get_journey()["id"] == journey["id"]
    restored.add_author("Autora")
    restored.runtime_log.close()
    again = Store(tmp_path / "global_stats.json")
    events = again.get_events()
    assert len(events) == 2
    assert len({(e["operation_id"], e["index"]) for e in events}) == 2
    assert sum(r["operation"] == "history_failed" for r in records(tmp_path)) == 1
    assert sum(r["operation"] == "history_saved" and r.get("event") == "journey_created"
               for r in records(tmp_path)) == 1
    again.runtime_log.close()


def test_failed_commit_logs_traceback_and_keeps_revision(tmp_path, capsys):
    store = Store(tmp_path / "global_stats.json", log_config=LogConfig("DEBUG"))
    before = store.storage.revision
    with patch.object(store.storage, "commit", side_effect=OSError("secret-disk-error")):
        with pytest.raises(DomainError):
            store.create_journey("Secret-title")
    assert store.storage.revision == before and store.get_journey() is None
    error = next(r for r in records(tmp_path) if r["level"] == "ERROR")
    assert error["phase"] == "persistence" and error["operation"] == "create_journey"
    assert error["traceback"][0]["type"] == "OSError"
    assert error["traceback"][0]["frames"]
    assert "secret-disk-error" not in json.dumps(records(tmp_path)) + capsys.readouterr().err
    assert not any(r["message"] == "Acción confirmada." for r in records(tmp_path))
    store.runtime_log.close()


def test_unexpected_http_error_and_debug_do_not_log_user_input(tmp_path, capsys):
    app = make_app(data_dir=tmp_path, log_config=LogConfig("DEBUG"))

    @app.get("/test/{private_id}")
    def broken(private_id: str):
        raise RuntimeError("secret-exception-content")

    status, _, body = request(app, "GET", "/test/secret-path?password=secret-query")
    assert status == 500
    assert "secret" not in body
    status, _, _ = request(app, "POST", "/api/journey", {"title": "secret-form-title"})
    assert status == 201
    content = json.dumps(records(tmp_path)) + capsys.readouterr().err
    assert all(secret not in content for secret in ("secret-path", "secret-query", "secret-exception-content", "secret-form-title"))
    errors = [r for r in records(tmp_path) if r["operation"] == "request_failed"]
    assert len(errors) == 1 and errors[0]["route"] == "/test/{private_id}"
    assert errors[0]["traceback"][0]["frames"][-1]["function"] == "broken"
    assert any(r["operation"] == "request_completed" and r["status"] == 500
               and r["duration_ms"] >= 0 for r in records(tmp_path))
    app.state.store.runtime_log.close()


def test_export_failures_keep_business_and_log_context(tmp_path):
    app = make_app(data_dir=tmp_path)
    store = app.state.store
    journey = store.create_journey("Privada")
    with patch("order_manager.store.build_export", side_effect=RuntimeError("secret-export-error")):
        status, _, _ = request(app, "POST", "/api/journey/close", {"journey_id": journey["id"]})
        assert status == 500
    assert store.get_journey()["id"] == journey["id"]
    assert store.get_globals()["journeys"] == 0
    store.close_journey()
    before = deepcopy(store.get_globals())
    with patch("order_manager.api.download_file", side_effect=RuntimeError("secret-zip-error")):
        status, _, _ = request(app, "GET", "/api/exports/last?format=zip")
        assert status == 500
    status, _, _ = request(app, "GET", "/api/exports/last?format=csv_summary")
    assert status == 200 and store.get_globals() == before
    errors = [r for r in records(tmp_path) if r["operation"] == "export_failed"]
    assert len(errors) == 2 and {r["format"] for r in errors} == {"json", "zip"}
    assert all(r["journey_id"] == journey["id"] for r in errors)
    assert "secret-" not in json.dumps(records(tmp_path))
    store.runtime_log.close()


def test_log_instances_do_not_cross_destinations_or_duplicate(tmp_path):
    first = RuntimeLog(tmp_path / "first")
    second = RuntimeLog(tmp_path / "second")
    first.record(logging.INFO, "Primera instancia.", "first")
    second.record(logging.INFO, "Segunda instancia.", "second")
    first.close()
    second.close()
    assert [r["operation"] for r in records(tmp_path / "first")] == ["first"]
    assert [r["operation"] for r in records(tmp_path / "second")] == ["second"]


def test_lifespan_closes_log_file(tmp_path):
    app = make_app(data_dir=tmp_path)

    async def run():
        async with app.router.lifespan_context(app):
            assert app.state.store.runtime_log.file.stream is not None

    asyncio.run(run())
    assert app.state.store.runtime_log.file.stream is None
    assert records(tmp_path)[-1]["operation"] == "shutdown"


def test_rotation_failure_is_reported_once_and_recovers(tmp_path, capsys):
    runtime = RuntimeLog(tmp_path, LogConfig("DEBUG", 1024, 2))
    with patch.object(runtime.file, "doRollover", side_effect=OSError("secret-rotation-error")):
        for _ in range(10):
            runtime.record(logging.DEBUG, "Diagnóstico de prueba.", "rotation_test")
        assert runtime.file.failed
    failed_output = capsys.readouterr().err
    assert failed_output.count('"operation": "logging_failed"') == 1
    assert "secret-rotation-error" not in failed_output
    runtime.record(logging.INFO, "Prueba de recuperación.", "recovered")
    assert not runtime.file.failed
    assert '"operation": "logging_recovered"' in capsys.readouterr().err
    assert records(tmp_path)[-1]["operation"] == "recovered"
    runtime.close()


def test_broken_console_does_not_prevent_persistent_log(tmp_path):
    runtime = RuntimeLog(tmp_path)

    class ClosedConsole:
        def write(self, value):
            raise OSError("Consola no disponible")

    runtime.console.setStream(ClosedConsole())
    runtime.record(logging.INFO, "Operación registrada.", "console_failure")
    assert records(tmp_path)[-1]["operation"] == "console_failure"
    runtime.close()
