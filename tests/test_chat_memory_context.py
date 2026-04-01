import json
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


def _save_turn(chat_id: str, idx: int) -> None:
    payload = {
        "short_answer": f"answer {idx}",
        "evidence": [f"evidence {idx}"],
        "limitations": [],
        "used_issue_ids": [f"YT-{idx}", f"YT-{idx}-B"],
    }
    history_store.save_history(
        query_text=f"query {idx}",
        query_mode="general_search",
        answer_text=json.dumps(payload, ensure_ascii=False),
        found_issue_ids=f"YT-{idx}",
        chat_id=chat_id,
    )


def test_memory_digest_uses_only_last_4_turns(monkeypatch, tmp_path):
    _init_temp_history_db(monkeypatch, tmp_path)
    live_chat = history_store.create_chat_session(title="live", dataset_id="ds_live")

    for i in range(6):
        _save_turn(live_chat["id"], i)

    digest = service._build_chat_memory_digest(live_chat["id"], "ai_answer")

    assert "query 0" not in digest
    assert "query 1" not in digest
    assert "query 2" in digest
    assert "query 5" in digest
    assert digest.count("turn=") == 4


def test_memory_digest_is_compact_and_digest_based(monkeypatch, tmp_path):
    _init_temp_history_db(monkeypatch, tmp_path)
    live_chat = history_store.create_chat_session(title="live", dataset_id="ds_live")

    payload = {
        "short_answer": "brief answer",
        "evidence": ["evidence line"],
        "limitations": [],
        "used_issue_ids": ["YT-1", "YT-2", "YT-3", "YT-4", "YT-5", "YT-6"],
        "tasks": [{"issue_id": "YT-X", "summary": "raw task should never be copied"}],
        "raw_blob": "X" * 5000,
    }
    history_store.save_history(
        query_text="query with very long answer",
        query_mode="general_search",
        answer_text=json.dumps(payload, ensure_ascii=False),
        found_issue_ids="YT-1",
        chat_id=live_chat["id"],
    )

    digest = service._build_chat_memory_digest(live_chat["id"], "ai_answer")

    assert "raw task should never be copied" not in digest
    assert "raw_blob" not in digest
    assert len(digest) <= service._MEMORY_TOTAL_CHARS

    used_part = digest.split("assistant_used_issue_ids=", 1)[1].split(";", 1)[0]
    used_ids = [x.strip() for x in used_part.split(",") if x.strip()]
    assert len(used_ids) <= service._MEMORY_USED_IDS_LIMIT


def test_memory_only_for_ai_answer_mode(monkeypatch, tmp_path):
    _init_temp_history_db(monkeypatch, tmp_path)
    live_chat = history_store.create_chat_session(title="live", dataset_id="ds_live")
    _save_turn(live_chat["id"], 1)

    assert service._build_chat_memory_digest(live_chat["id"], "precise") == ""
    assert service._build_chat_memory_digest(live_chat["id"], "auto") == ""
    assert service._build_chat_memory_digest(live_chat["id"], "ai_answer") != ""


def test_memory_not_built_for_stale_or_archived_chat(monkeypatch, tmp_path):
    _init_temp_history_db(monkeypatch, tmp_path)

    stale_chat = history_store.create_chat_session(title="stale", dataset_id="ds_old")
    live_chat = history_store.create_chat_session(title="live", dataset_id="ds_new")
    _save_turn(stale_chat["id"], 1)
    _save_turn(live_chat["id"], 2)

    monkeypatch.setattr(service, "load_active_dataset_metadata", lambda: {"dataset_id": "ds_new"})

    seen = []

    def _fake_run_agent(_, chat_id="", memory_context=""):
        seen.append({"chat_id": chat_id, "memory_context": memory_context})
        return {"mode": "general_search", "short_answer": "ok", "used_issue_ids": []}

    monkeypatch.setattr(service, "run_agent", _fake_run_agent)

    service.run_agent_web("stale question", "ai_answer", chat_id=stale_chat["id"])
    service.run_agent_web("live question", "ai_answer", chat_id=live_chat["id"])

    assert seen[0]["chat_id"] == ""
    assert seen[0]["memory_context"] == ""
    assert seen[1]["chat_id"] == live_chat["id"]
    assert "assistant_short_answer_digest=answer 2" in seen[1]["memory_context"]


def test_same_memory_policy_for_query_and_query_stream(monkeypatch, tmp_path):
    _init_temp_history_db(monkeypatch, tmp_path)
    live_chat = history_store.create_chat_session(title="live", dataset_id="ds_new")
    _save_turn(live_chat["id"], 10)

    monkeypatch.setattr(service, "load_active_dataset_metadata", lambda: {"dataset_id": "ds_new"})

    seen = {"query_memory": "", "stream_memory": ""}

    def _fake_run_agent(_, chat_id="", memory_context=""):
        seen["query_memory"] = memory_context
        return {"mode": "general_search", "short_answer": "ok", "used_issue_ids": []}

    monkeypatch.setattr(service, "run_agent", _fake_run_agent)
    service.run_agent_web("q query", "ai_answer", chat_id=live_chat["id"])

    monkeypatch.setattr(service, "detect_intent", lambda _: {"mode": "general_search", "query": "q stream"})
    monkeypatch.setattr(
        service,
        "hybrid_search",
        lambda *_args, **_kwargs: [{"issue_id": "YT-10", "summary": "s", "status": "Open"}],
    )

    def _fake_prompt(_query, _tasks, _mode, analysis_profile="fast", extra_context="", memory_context=""):
        seen["stream_memory"] = memory_context
        return "prompt"

    monkeypatch.setattr(service, "build_llm_prompt", _fake_prompt)
    monkeypatch.setattr(
        service.ollama_client,
        "generate_stream",
        lambda _prompt: iter(
            ['{"short_answer":"ok","evidence":["fact"],"limitations":[],"used_issue_ids":["YT-10"]}']
        ),
    )

    list(service.stream_agent_service("q stream", "ai_answer", chat_id=live_chat["id"]))

    assert seen["query_memory"]
    assert seen["stream_memory"]
    assert seen["query_memory"] == seen["stream_memory"]
