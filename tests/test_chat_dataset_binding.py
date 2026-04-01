import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import history_store
from web import service


def _init_temp_history_db(monkeypatch, tmp_path):
    db_file = tmp_path / "agent_history.db"
    monkeypatch.setattr(history_store, "SQLITE_HISTORY_FILE", db_file)
    history_store.init_history_db()
    return db_file


def test_chat_sessions_store_dataset_and_archive_status(monkeypatch, tmp_path):
    _init_temp_history_db(monkeypatch, tmp_path)

    live = history_store.create_chat_session(title="live", dataset_id="ds_live")
    stale = history_store.create_chat_session(title="stale", dataset_id="ds_old")
    legacy = history_store.create_chat_session(title="legacy")

    rows = history_store.list_chat_sessions(limit=20, active_dataset_id="ds_live")
    by_id = {row["id"]: row for row in rows}

    assert by_id[live["id"]]["dataset_id"] == "ds_live"
    assert by_id[live["id"]]["is_archived"] is False

    assert by_id[stale["id"]]["dataset_id"] == "ds_old"
    assert by_id[stale["id"]]["is_archived"] is True

    assert by_id[legacy["id"]]["dataset_id"] == ""
    assert by_id[legacy["id"]]["is_archived"] is True

    rows_without_active = history_store.list_chat_sessions(limit=20, active_dataset_id="")
    assert all(row["is_archived"] is False for row in rows_without_active)


def test_is_chat_session_live_truth_table(monkeypatch, tmp_path):
    _init_temp_history_db(monkeypatch, tmp_path)

    live = history_store.create_chat_session(title="live", dataset_id="ds_live")
    stale = history_store.create_chat_session(title="stale", dataset_id="ds_old")
    legacy = history_store.create_chat_session(title="legacy")

    assert history_store.is_chat_session_live(live["id"], "ds_live") is True
    assert history_store.is_chat_session_live(stale["id"], "ds_live") is False
    assert history_store.is_chat_session_live(legacy["id"], "ds_live") is False

    # No active dataset means we do not archive by dataset mismatch.
    assert history_store.is_chat_session_live(stale["id"], "") is True

    assert history_store.is_chat_session_live("missing_chat", "ds_live") is False
    assert history_store.is_chat_session_live("", "ds_live") is False


def test_stream_service_ignores_stale_chat_id(monkeypatch, tmp_path):
    _init_temp_history_db(monkeypatch, tmp_path)

    stale_chat = history_store.create_chat_session(title="stale", dataset_id="ds_old")
    live_chat = history_store.create_chat_session(title="live", dataset_id="ds_new")

    monkeypatch.setattr(service, "load_active_dataset_metadata", lambda: {"dataset_id": "ds_new"})
    monkeypatch.setattr(service, "detect_intent", lambda _: {"mode": "exact_search"})
    monkeypatch.setattr(
        service,
        "run_agent",
        lambda _: {"mode": "exact_search", "short_answer": "ok", "used_issue_ids": []},
    )

    list(service.stream_agent_service("test stale", "ai_answer", chat_id=stale_chat["id"]))
    list(service.stream_agent_service("test live", "ai_answer", chat_id=live_chat["id"]))

    assert history_store.get_chat_messages(stale_chat["id"]) == []
    assert len(history_store.get_chat_messages(live_chat["id"])) == 1
