import json
import requests
from time import perf_counter
from typing import Generator

from src.data_prepare import save_prepared_tasks, has_prepared_tasks
from src.vector_store import rebuild_index, has_ready_index
from src.agent import run_agent
from src.history_store import get_last_history, save_history
from src.config import OLLAMA_HOST

from src.query_parser import detect_intent
from src.search_engine import hybrid_search
from src.prompts import build_llm_prompt
from src.ollama_client import ollama_client
from src.response_parser import parse_json_safely, validate_llm_result
from src.answer_builder import llm_result, fallback_result


_STREAMING_MODES = {"similar", "analyze_new_task", "general_search"}


def check_ollama() -> bool:
    """
    Честный health-check Ollama:
    проверяем /api/tags и наличие ключа models.
    """
    try:
        url = f"{OLLAMA_HOST.rstrip('/')}/api/tags"
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        data = r.json()
        return isinstance(data, dict) and "models" in data
    except Exception:
        return False


def get_system_status() -> dict:
    return {
        "prepared_data": has_prepared_tasks(),
        "index_ready": has_ready_index(),
        "ollama_ready": check_ollama(),
    }


def prepare_data_action() -> dict:
    tasks, report = save_prepared_tasks()
    return {
        "tasks_total": len(tasks),
        "report_lines": report,
    }


def rebuild_index_action() -> dict:
    return rebuild_index()


def run_agent_web(query: str, mode: str) -> dict:
    query = query.strip()

    if mode == "exact":
        routed_query = f"точно {query}"
    elif mode == "llm":
        routed_query = f"общий {query}"
    else:
        routed_query = query

    return run_agent(routed_query)


def get_history_action(limit: int = 20):
    return get_last_history(limit=limit)


def _route_query(query: str, web_mode: str) -> str:
    query = query.strip()
    if web_mode == "exact":
        return f"точно {query}"
    if web_mode == "llm":
        return f"общий {query}"
    return query


def stream_agent_service(query: str, web_mode: str) -> Generator[str, None, None]:
    started = perf_counter()
    routed_query = _route_query(query, web_mode)
    intent = detect_intent(routed_query)
    intent_mode = intent["mode"]

    # Для не-LLM режимов не стримим токены, а просто шлем final result
    if intent_mode not in _STREAMING_MODES:
        result = run_agent(routed_query)
        yield f"event: result\ndata: {json.dumps(result, ensure_ascii=False)}\n\n"
        yield "event: done\ndata: {}\n\n"
        return

    search_query = intent.get("query", routed_query)
    tasks = hybrid_search(search_query, top_k=5)
    retrieved_ids = [t["issue_id"] for t in tasks]

    if not tasks:
        result = fallback_result(
            intent_mode,
            [],
            "Подходящие задачи не найдены.",
            extra_limitations=["Для ответа не найдено релевантных задач."],
        )
        result["used_llm"] = False
        result["duration_ms"] = int((perf_counter() - started) * 1000)

        yield f"event: result\ndata: {json.dumps(result, ensure_ascii=False)}\n\n"
        yield "event: done\ndata: {}\n\n"

        _save_stream_history(routed_query, intent_mode, result, retrieved_ids, started, llm_used=0)
        return

    prompt = build_llm_prompt(routed_query, tasks, intent_mode)

    full_text = ""
    try:
        for token in ollama_client.generate_stream(prompt):
            full_text += token
            payload = json.dumps({"text": token}, ensure_ascii=False)
            yield f"event: token\ndata: {payload}\n\n"
    except Exception as e:
        result = fallback_result(
            intent_mode,
            tasks,
            "Ошибка во время стриминга LLM.",
            extra_limitations=[str(e)],
        )
        result["used_llm"] = False
        result["duration_ms"] = int((perf_counter() - started) * 1000)

        yield f"event: result\ndata: {json.dumps(result, ensure_ascii=False)}\n\n"
        yield "event: done\ndata: {}\n\n"

        _save_stream_history(routed_query, intent_mode, result, retrieved_ids, started, llm_used=0)
        return

    llm_used = 0
    try:
        parsed = parse_json_safely(full_text)
        parsed = validate_llm_result(parsed, tasks)
        result = llm_result(parsed, intent_mode, tasks)
        result["used_llm"] = True
        llm_used = 1
    except Exception as e:
        result = fallback_result(
            intent_mode,
            tasks,
            "Ошибка разбора ответа LLM.",
            extra_limitations=[str(e)],
        )
        result["used_llm"] = False

    result["duration_ms"] = int((perf_counter() - started) * 1000)

    yield f"event: result\ndata: {json.dumps(result, ensure_ascii=False)}\n\n"
    yield "event: done\ndata: {}\n\n"

    _save_stream_history(routed_query, intent_mode, result, retrieved_ids, started, llm_used=llm_used)


def _save_stream_history(
    query: str,
    mode: str,
    result: dict,
    retrieved_ids: list[str],
    started: float,
    llm_used: int,
) -> None:
    try:
        save_history(
            query_text=query,
            query_mode=mode,
            answer_text=json.dumps(result, ensure_ascii=False),
            found_issue_ids=", ".join(result.get("used_issue_ids", [])),
            retrieved_candidates=", ".join(retrieved_ids),
            duration_ms=int((perf_counter() - started) * 1000),
            llm_used=llm_used,
            error_text="",
        )
    except Exception:
        pass