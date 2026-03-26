import requests

from src.data_prepare import save_prepared_tasks, has_prepared_tasks
from src.vector_store import rebuild_index, has_ready_index
from src.agent import run_agent
from src.history_store import get_last_history
from src.config import OLLAMA_HOST


def check_ollama() -> bool:
    try:
        r = requests.get(OLLAMA_HOST, timeout=3)
        return r.status_code < 500
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