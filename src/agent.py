import json

from src.query_parser import detect_intent
from src.search_engine import (
    find_task_by_id,
    filter_tasks,
    hybrid_search,
    exact_search,
    find_related_tasks,
    aggregate_counts,
    upcoming_deadlines,
)
from src.prompts import build_llm_prompt
from src.ollama_client import ollama_client
from src.response_parser import parse_json_safely
from src.answer_builder import (
    task_card,
    task_list,
    count_result,
    deadlines_result,
    llm_result,
    fallback_result,
)
from src.history_store import save_history


def _call_llm_or_fallback(user_query: str, mode: str, tasks: list[dict], fallback_message: str) -> dict:
    """
    Пытается получить структурированный ответ от LLM.
    Если LLM не ответила, вернула плохой JSON или пустой ответ —
    возвращается детерминированный fallback.
    """
    prompt = build_llm_prompt(user_query, tasks, mode)

    try:
        raw = ollama_client.generate(prompt)

        if not raw or not raw.strip():
            return fallback_result(
                mode,
                tasks,
                fallback_message,
                extra_limitations=["LLM вернула пустой ответ."],
            )

        parsed = parse_json_safely(raw)
        result = llm_result(parsed, mode, tasks)

        # Явно помечаем, что ответ пришел от LLM.
        result["used_llm"] = True
        return result

    except Exception as e:
        result = fallback_result(
            mode,
            tasks,
            fallback_message,
            extra_limitations=[f"Причина fallback: {e}"],
        )
        result["used_llm"] = False
        return result

def _apply_filters(filters: dict) -> list[dict]:
    return filter_tasks(
        status=filters.get("status"),
        status_group=filters.get("status_group"),
        workflow_group=filters.get("workflow_group"),
        priority=filters.get("priority"),
        doc_type=filters.get("doc_type"),
        functional_customer=filters.get("functional_customer"),
        responsible_dit=filters.get("responsible_dit"),
    )


def run_agent(user_query: str) -> dict:
    intent = detect_intent(user_query)
    mode = intent["mode"]

    if mode == "help":
        result = {
            "mode": "help",
            "short_answer": "Введи help в главном меню, чтобы увидеть список команд.",
            "evidence": [],
            "limitations": [],
            "used_issue_ids": [],
            "used_llm": False,
        }
        save_history(user_query, mode, json.dumps(result, ensure_ascii=False), "")
        return result

    if mode == "task_by_id":
        task = find_task_by_id(intent["issue_id"])

        if task is None:
            result = {
                "mode": mode,
                "short_answer": f"Задача {intent['issue_id']} не найдена.",
                "evidence": [],
                "limitations": ["Проверь ID задачи или обнови выгрузку."],
                "used_issue_ids": [],
                "used_llm": False,
            }
        else:
            result = task_card(task)
            related = find_related_tasks(task, limit=3)

            # Даже если related нет, основной ID должен быть сохранен.
            result["used_issue_ids"] = [task["issue_id"]]
            result["used_llm"] = False

            if related:
                result["tasks"] = [task] + related
                result["evidence"].append("Добавлены логически близкие задачи по совпадению полей и текста.")
                result["used_issue_ids"] = [t["issue_id"] for t in [task] + related]
                result["used_llm"] = False
    elif mode == "list":
        tasks = _apply_filters(intent["filters"])
        result = task_list("Список задач по фильтрам", tasks[:30])
        if len(tasks) > 30:
            result["limitations"].append("Показаны первые 30 задач.")
        result["used_llm"] = False

    elif mode == "count":
        tasks = _apply_filters(intent.get("filters", {}))
        items = aggregate_counts(intent["field"], tasks)
        result = count_result(intent["field"], items)
        result["used_llm"] = False

    elif mode == "deadlines":
        items = upcoming_deadlines(days=intent["days"])
        result = deadlines_result(items, intent["days"])
        result["used_llm"] = False
    
    elif mode == "exact_search":
        tasks = exact_search(intent["query"], top_k=10)
        result = task_list("Детерминированный поиск без LLM", tasks)
        result["limitations"].append("LLM не использовалась.")
        result["used_llm"] = False

    elif mode == "similar":
        tasks = hybrid_search(intent["query"], top_k=5)
        result = _call_llm_or_fallback(
            user_query,
            mode,
            tasks,
            "Показаны наиболее похожие задачи по lexical + semantic retrieval.",
        )

    elif mode == "analyze_new_task":
        tasks = hybrid_search(intent["query"], top_k=5)
        result = _call_llm_or_fallback(
            user_query,
            mode,
            tasks,
            "Показаны ближайшие аналоги для новой формулировки.",
        )

    else:
        tasks = hybrid_search(intent.get("query", user_query), top_k=5)
        result = _call_llm_or_fallback(
            user_query,
            mode,
            tasks,
            "Показаны ближайшие задачи по свободному запросу.",
        )

    try:
        save_history(
            query_text=user_query,
            query_mode=mode,
            answer_text=json.dumps(result, ensure_ascii=False),
            found_issue_ids=", ".join(result.get("used_issue_ids", [])),
        )
    except Exception as e:
        # История не должна ломать основной ответ агента.
        result.setdefault("limitations", []).append(f"История не была сохранена: {e}")

    return result
