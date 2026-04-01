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
    seen_chat_ids = []

    def _fake_run_agent(_, chat_id="", memory_context=""):
        seen_chat_ids.append(chat_id)
        return {"mode": "exact_search", "short_answer": "ok", "used_issue_ids": []}

    monkeypatch.setattr(
        service,
        "run_agent",
        _fake_run_agent,
    )

    list(service.stream_agent_service("test stale", "ai_answer", chat_id=stale_chat["id"]))
    list(service.stream_agent_service("test live", "ai_answer", chat_id=live_chat["id"]))

    assert seen_chat_ids == ["", live_chat["id"]]


def test_run_agent_web_applies_live_chat_policy(monkeypatch, tmp_path):
    _init_temp_history_db(monkeypatch, tmp_path)

    stale_chat = history_store.create_chat_session(title="stale", dataset_id="ds_old")
    live_chat = history_store.create_chat_session(title="live", dataset_id="ds_new")

    history_store.save_history(
        query_text="old q",
        query_mode="general_search",
        answer_text='{"short_answer":"old answer","used_issue_ids":[],"evidence":["old ev"]}',
        found_issue_ids="",
        chat_id=stale_chat["id"],
    )
    history_store.save_history(
        query_text="live q",
        query_mode="general_search",
        answer_text='{"short_answer":"live answer","used_issue_ids":["YT-1"],"evidence":["live ev"]}',
        found_issue_ids="YT-1",
        chat_id=live_chat["id"],
    )

    monkeypatch.setattr(service, "load_active_dataset_metadata", lambda: {"dataset_id": "ds_new"})

    seen = []

    def _fake_run_agent(_, chat_id="", memory_context=""):
        seen.append({"chat_id": chat_id, "memory_context": memory_context})
        return {"mode": "general_search", "short_answer": "ok", "used_issue_ids": []}

    monkeypatch.setattr(service, "run_agent", _fake_run_agent)

    service.run_agent_web("q stale", "ai_answer", chat_id=stale_chat["id"])
    service.run_agent_web("q live", "ai_answer", chat_id=live_chat["id"])

    assert seen[0]["chat_id"] == ""
    assert seen[0]["memory_context"] == ""

    assert seen[1]["chat_id"] == live_chat["id"]
    assert "turn=1" in seen[1]["memory_context"]
    assert "assistant_short_answer_digest=live answer" in seen[1]["memory_context"]
