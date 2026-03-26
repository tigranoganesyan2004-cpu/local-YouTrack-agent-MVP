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
from src.response_parser import parse_json_safely, validate_llm_result
from time import perf_counter
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
    Либо получаем валидный структурированный ответ от LLM,
    либо уходим в безопасный fallback без фантазии.
    """
    if not tasks:
        result = fallback_result(
            mode,
            [],
            "Подходящие задачи не найдены.",
            extra_limitations=["Для ответа не найдено релевантных задач."]
        )
        result["used_llm"] = False
        return result

    prompt = build_llm_prompt(user_query, tasks, mode)

    try:
        raw = ollama_client.generate(prompt)
        parsed = parse_json_safely(raw)
        parsed = validate_llm_result(parsed, tasks)

        result = llm_result(parsed, mode, tasks)
        result["used_llm"] = True
        return result

    except Exception as e:
        result = fallback_result(
            mode,
            tasks,
            fallback_message,
            extra_limitations=[f"Причина fallback: {e}"]
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
    started = perf_counter()
    error_text = ""
    llm_used = 0
    retrieved_candidates = []

    intent = detect_intent(user_query)
    mode = intent["mode"]

    if mode == "help":
        result = {
            "mode": "help",
            "short_answer": "Напиши 'помощь' в чате, чтобы увидеть список русских команд.",
            "evidence": [],
            "limitations": [],
            "used_issue_ids": [],
            "used_llm": False,
        }
        try:
            save_history(
                query_text=user_query,
                query_mode=mode,
                answer_text=json.dumps(result, ensure_ascii=False),
                found_issue_ids="",
                retrieved_candidates="",
                duration_ms=int((perf_counter() - started) * 1000),
                llm_used=0,
                error_text="",
            )
        except Exception:
            pass
        return result

    try:
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
                result["used_issue_ids"] = [task["issue_id"]]
                result["used_llm"] = False

                if related:
                    result["tasks"] = [task] + related
                    result["evidence"].append("Добавлены логически близкие задачи по совпадению полей и текста.")
                    result["used_issue_ids"] = [t["issue_id"] for t in [task] + related]

        elif mode == "list":
            tasks = _apply_filters(intent["filters"])
            retrieved_candidates = [t["issue_id"] for t in tasks]
            result = task_list("Список задач по фильтрам", tasks[:30])
            if len(tasks) > 30:
                result["limitations"].append("Показаны первые 30 задач.")
            result["used_llm"] = False

        elif mode == "count":
            tasks = _apply_filters(intent.get("filters", {}))
            retrieved_candidates = [t["issue_id"] for t in tasks]
            items = aggregate_counts(intent["field"], tasks)
            result = count_result(intent["field"], items)
            result["used_llm"] = False

        elif mode == "deadlines":
            items = upcoming_deadlines(days=intent["days"])
            retrieved_candidates = [x["issue_id"] for x in items]
            result = deadlines_result(items, intent["days"])
            result["used_llm"] = False

        elif mode == "exact_search":
            tasks = exact_search(intent["query"], top_k=10)
            retrieved_candidates = [t["issue_id"] for t in tasks]
            result = task_list("Детерминированный поиск без LLM", tasks)
            result["limitations"].append("LLM не использовалась.")
            result["used_llm"] = False

        elif mode == "similar":
            tasks = hybrid_search(intent["query"], top_k=5)
            retrieved_candidates = [t["issue_id"] for t in tasks]
            result = _call_llm_or_fallback(
                user_query,
                mode,
                tasks,
                "Показаны наиболее похожие задачи по lexical + semantic retrieval.",
            )

        elif mode == "analyze_new_task":
            tasks = hybrid_search(intent["query"], top_k=5)
            retrieved_candidates = [t["issue_id"] for t in tasks]
            result = _call_llm_or_fallback(
                user_query,
                mode,
                tasks,
                "Показаны ближайшие аналоги для новой формулировки.",
            )

        else:
            tasks = hybrid_search(intent.get("query", user_query), top_k=5)
            retrieved_candidates = [t["issue_id"] for t in tasks]
            result = _call_llm_or_fallback(
                user_query,
                mode,
                tasks,
                "Показаны ближайшие задачи по свободному запросу.",
            )

        llm_used = 1 if result.get("used_llm") else 0

    except Exception as e:
        error_text = str(e)
        result = fallback_result(
            "system_error",
            [],
            "Во время обработки запроса произошла ошибка.",
            extra_limitations=[error_text],
        )
        result["used_llm"] = False
        llm_used = 0

    duration_ms = int((perf_counter() - started) * 1000)

    try:
        save_history(
            query_text=user_query,
            query_mode=mode,
            answer_text=json.dumps(result, ensure_ascii=False),
            found_issue_ids=", ".join(result.get("used_issue_ids", [])),
            retrieved_candidates=", ".join(retrieved_candidates),
            duration_ms=duration_ms,
            llm_used=llm_used,
            error_text=error_text,
        )
    except Exception:
        pass

    return result
