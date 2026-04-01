import csv
import io
import json
import requests
from collections import Counter
from pathlib import Path
from time import perf_counter
from typing import Generator

from src.agent import run_agent
from src.answer_builder import fallback_result, llm_result
from src.config import DATASET_REPORT_JSON, OLLAMA_HOST, TASKS_JSON
from src.data_prepare import has_prepared_tasks, save_prepared_tasks
from src.history_store import get_last_history, save_history
from src.ollama_client import ollama_client
from src.prompts import build_llm_prompt
from src.query_parser import detect_intent
from src.response_parser import parse_json_safely, validate_llm_result
from src.search_engine import (
    dataset_kpis,
    hybrid_search,
    load_tasks,
)
from src.utils import load_json, normalize_space, safe_str
from src.vector_store import has_ready_index, rebuild_index


# web/service.py — серверный слой для Web UI.
# Здесь мы не рендерим HTML, а:
# - готовим status / dashboard данные
# - собираем bootstrap для UI
# - отдаем подсказки и примеры
# - делаем экспорт результатов
# - обслуживаем SSE-стрим
#
# Важно:
# 1. Не ломаем текущий фронт.
# 2. Добавляем новые серверные эндпоинты для будущего UI.
# 3. Стараемся не пересчитывать тяжелые вещи на каждый запрос.

_STREAMING_MODES = {"similar", "analyze_new_task", "general_search"}

_UI_CACHE = {
    "tasks_mtime": None,
    "report_mtime": None,
    "payload": None,
}


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


def _route_query(query: str, web_mode: str) -> str:
    query = query.strip()

    # Public mode: "precise" (Precise Mode button) — deterministic exact search, no LLM.
    # Internal compat: "exact" still accepted from direct API callers.
    if web_mode in {"precise", "exact"}:
        return f"точно {query}"

    # Public mode: "ai_answer" (AI Answer button) — grounded LLM synthesis path.
    if web_mode == "ai_answer":
        return f"общий {query}"

    # Internal compat only — not reachable from the public web UI.
    if web_mode == "llm":
        return f"общий {query}"

    # "deep" is intentionally not mapped from the public UI.
    # Kept as a no-op guard so direct callers don't accidentally activate it.

    # Default ("auto" / anything else) — NL intent detection decides internally.
    return query


def run_agent_web(query: str, mode: str) -> dict:
    routed_query = _route_query(query, mode)
    return run_agent(routed_query)


def get_history_action(limit: int = 20):
    return get_last_history(limit=limit)


def prepare_data_action() -> dict:
    tasks, report = save_prepared_tasks()

    # После подготовки данных нужно сбросить UI cache,
    # иначе dashboard и suggestions могут показывать старые значения.
    _invalidate_ui_cache()

    return {
        "tasks_total": len(tasks),
        "report_lines": report,
    }


def rebuild_index_action() -> dict:
    result = rebuild_index()
    return result


def _safe_file_mtime(path: Path) -> float | None:
    if not path.exists():
        return None
    try:
        return path.stat().st_mtime
    except Exception:
        return None


def _invalidate_ui_cache() -> None:
    _UI_CACHE["tasks_mtime"] = None
    _UI_CACHE["report_mtime"] = None
    _UI_CACHE["payload"] = None


def _load_dataset_report() -> dict:
    if not DATASET_REPORT_JSON.exists():
        return {}

    try:
        data = load_json(DATASET_REPORT_JSON)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _top_values(tasks: list[dict], field: str, limit: int = 10) -> list[tuple[str, int]]:
    counter = Counter()

    for task in tasks:
        value = safe_str(task.get(field))
        if value:
            counter[value] += 1

    return counter.most_common(limit)


def _top_issue_ids(tasks: list[dict], limit: int = 20) -> list[str]:
    ids = []
    for task in tasks:
        issue_id = safe_str(task.get("issue_id"))
        if issue_id:
            ids.append(issue_id)

    ids = sorted(set(ids))
    return ids[:limit]


def _build_lookup_catalog(tasks: list[dict]) -> dict:
    """
    Готовим lookup-данные для UI:
    - ids
    - customers
    - responsibles
    - statuses
    - doc_types
    - approval stages

    Эти данные потом используются в автодополнении и примерах.
    """
    ids = []
    customers = set()
    responsibles = set()
    statuses = set()
    doc_types = set()
    approval_stages = set()

    for task in tasks:
        issue_id = safe_str(task.get("issue_id"))
        if issue_id:
            ids.append(issue_id)

        value = safe_str(task.get("functional_customer"))
        if value:
            customers.add(value)

        value = safe_str(task.get("responsible_dit"))
        if value:
            responsibles.add(value)

        value = safe_str(task.get("status"))
        if value:
            statuses.add(value)

        value = safe_str(task.get("doc_type"))
        if value:
            doc_types.add(value)

        value = safe_str(task.get("current_approval_stage"))
        if value:
            approval_stages.add(value)

    return {
        "ids": sorted(set(ids)),
        "customers": sorted(customers),
        "responsibles": sorted(responsibles),
        "statuses": sorted(statuses),
        "doc_types": sorted(doc_types),
        "approval_stages": sorted(approval_stages),
    }


def _first_or_fallback(values: list[str], fallback: str) -> str:
    for value in values:
        value = safe_str(value)
        if value:
            return value
    return fallback


def _build_example_categories(tasks: list[dict]) -> list[dict]:
    """
    Категории примеров для UI.
    Стараемся подставлять реальные значения из датасета, чтобы подсказки были живыми.
    """
    lookups = _build_lookup_catalog(tasks)

    sample_id = _first_or_fallback(lookups["ids"], "EAIST_SGL-350")
    sample_customer = _first_or_fallback(lookups["customers"], "ГКУ")
    sample_responsible = _first_or_fallback(lookups["responsibles"], "SAA_1")

    return [
        {
            "id": "by_id",
            "title": "Поиск по ID",
            "examples": [
                f"Покажи задачу {sample_id}",
                f"Покажи карточку задачи {sample_id}",
                f"Что по задаче {sample_id}",
            ],
        },
        {
            "id": "approvals",
            "title": "Согласования",
            "examples": [
                "Что ждёт согласования от ДИТ?",
                "Какие задачи ждут согласования от ГКУ?",
                "У каких задач решение ДИТ ещё не принято?",
                "Покажи задачи, где согласование с ДЭПиР ещё не завершено",
            ],
        },
        {
            "id": "deadlines",
            "title": "Сроки и просрочки",
            "examples": [
                "Какие задачи просрочены?",
                "Покажи задачи где срок устранения замечаний уже прошёл",
                "Какие сроки согласования истекают в ближайшие 7 дней?",
                "Какие сроки горят в ближайшие 10 дней?",
            ],
        },
        {
            "id": "analytics",
            "title": "Аналитика",
            "examples": [
                "Статистика по статусам",
                "Сколько задач у каждого заказчика?",
                "Статистика по текущим стадиям согласования",
                "Сколько задач у каждого ответственного?",
            ],
        },
        {
            "id": "by_customer",
            "title": "По заказчику",
            "examples": [
                f"Задачи по заказчику {sample_customer}",
                f"Покажи постановки по заказчику {sample_customer}",
                f"Задачи {sample_customer} на согласовании",
            ],
        },
        {
            "id": "by_responsible",
            "title": "По ответственному",
            "examples": [
                f"Задачи где ответственный {sample_responsible}",
                f"Что сейчас у {sample_responsible}",
                f"Покажи активные задачи у {sample_responsible}",
            ],
        },
        {
            "id": "topic_search",
            "title": "По теме",
            "examples": [
                "Найди задачи по уведомлениям пользователям",
                "Похожие задачи по СПГЗ",
                "Проанализируй новую задачу: рассылка уведомлений в мессенджер",
            ],
        },
    ]


def _build_dashboard(tasks: list[dict], report: dict) -> dict:
    """
    Dashboard для UI.
    Берем:
    - KPI по текущему tasks.json
    - top-списки из report, если они есть
    """
    kpis = dataset_kpis(tasks)

    top_statuses = report.get("top_statuses", [])
    top_customers = report.get("top_functional_customers", []) or _top_values(tasks, "functional_customer", limit=8)
    top_responsibles = report.get("top_responsibles", []) or _top_values(tasks, "responsible_dit", limit=8)
    top_doc_types = report.get("top_doc_types", []) or _top_values(tasks, "doc_type", limit=8)
    top_stages = report.get("top_current_approval_stages", []) or _top_values(tasks, "current_approval_stage", limit=8)

    return {
        "kpis": {
            "total": kpis.get("total", 0),
            "active": kpis.get("active", 0),
            "final": kpis.get("final", 0),
            "overdue": kpis.get("overdue", 0),
            "with_remarks": kpis.get("with_remarks", 0),
            "pending_approvals": kpis.get("pending_approvals", 0),
        },
        "top_statuses": top_statuses[:8],
        "top_customers": top_customers[:8],
        "top_responsibles": top_responsibles[:8],
        "top_doc_types": top_doc_types[:8],
        "top_current_approval_stages": top_stages[:8],
    }


def _build_status_payload(tasks: list[dict], report: dict) -> dict:
    kpis = dataset_kpis(tasks)

    payload = {
        # backward-compatible поля
        "prepared_data": has_prepared_tasks(),
        "index_ready": has_ready_index(),
        "ollama_ready": check_ollama(),
        # новые dashboard-friendly поля
        "tasks_total": kpis.get("total", 0),
        "active_total": kpis.get("active", 0),
        "final_total": kpis.get("final", 0),
        "overdue_total": kpis.get("overdue", 0),
        "with_remarks_total": kpis.get("with_remarks", 0),
        "pending_approvals_total": kpis.get("pending_approvals", 0),
        "source_files": report.get("source_files", {}),
    }

    return payload


def _build_ui_payload() -> dict:
    tasks_mtime = _safe_file_mtime(TASKS_JSON)
    report_mtime = _safe_file_mtime(DATASET_REPORT_JSON)

    if (
        _UI_CACHE["payload"] is not None
        and _UI_CACHE["tasks_mtime"] == tasks_mtime
        and _UI_CACHE["report_mtime"] == report_mtime
    ):
        return _UI_CACHE["payload"]

    tasks = load_tasks()
    report = _load_dataset_report()
    lookups = _build_lookup_catalog(tasks)
    examples = _build_example_categories(tasks)
    dashboard = _build_dashboard(tasks, report)
    status = _build_status_payload(tasks, report)

    payload = {
        "status": status,
        "dashboard": dashboard,
        "lookups": lookups,
        "examples": examples,
    }

    _UI_CACHE["tasks_mtime"] = tasks_mtime
    _UI_CACHE["report_mtime"] = report_mtime
    _UI_CACHE["payload"] = payload
    return payload


def get_system_status() -> dict:
    """
    Старый endpoint /api/status продолжает работать,
    но теперь отдает расширенные данные.
    """
    payload = _build_ui_payload()
    return {
        **payload["status"],
        "dashboard": payload["dashboard"],
    }


def get_ui_bootstrap_action() -> dict:
    """
    Полный bootstrap для интерфейса:
    - status
    - dashboard
    - examples
    - lookups
    """
    return _build_ui_payload()


def _append_suggestion(target: list[dict], seen: set[str], kind: str, label: str, insert_text: str) -> None:
    key = f"{kind}|{insert_text}"
    if key in seen:
        return

    seen.add(key)
    target.append(
        {
            "type": kind,
            "label": label,
            "insert_text": insert_text,
        }
    )


def search_suggestions_action(query: str, limit: int = 10) -> list[dict]:
    """
    Подсказки для автодополнения.

    Возвращаем не просто строки, а объекты:
    - type
    - label
    - insert_text

    Чтобы фронт потом мог красиво рендерить разные типы.
    """
    payload = _build_ui_payload()
    lookups = payload["lookups"]

    q = normalize_space(query).lower()
    suggestions = []
    seen = set()

    # Если строка пустая — показываем несколько лучших шаблонов.
    if not q:
        for category in payload["examples"][:4]:
            for example in category.get("examples", [])[:2]:
                _append_suggestion(
                    suggestions,
                    seen,
                    "example",
                    f"{category.get('title', 'Пример')}: {example}",
                    example,
                )
                if len(suggestions) >= limit:
                    return suggestions
        return suggestions

    # ID
    for issue_id in lookups["ids"]:
        if q in issue_id.lower():
            _append_suggestion(
                suggestions,
                seen,
                "issue_id",
                f"ID задачи: {issue_id}",
                f"Покажи задачу {issue_id}",
            )
            if len(suggestions) >= limit:
                return suggestions

    # customers
    for value in lookups["customers"]:
        if q in value.lower():
            _append_suggestion(
                suggestions,
                seen,
                "customer",
                f"Заказчик: {value}",
                f"Задачи по заказчику {value}",
            )
            if len(suggestions) >= limit:
                return suggestions

    # responsibles
    for value in lookups["responsibles"]:
        if q in value.lower():
            _append_suggestion(
                suggestions,
                seen,
                "responsible",
                f"Ответственный: {value}",
                f"Задачи где ответственный {value}",
            )
            if len(suggestions) >= limit:
                return suggestions

    # statuses
    for value in lookups["statuses"]:
        if q in value.lower():
            _append_suggestion(
                suggestions,
                seen,
                "status",
                f"Статус: {value}",
                f'список status="{value}"',
            )
            if len(suggestions) >= limit:
                return suggestions

    # doc types
    for value in lookups["doc_types"]:
        if q in value.lower():
            _append_suggestion(
                suggestions,
                seen,
                "doc_type",
                f"Тип документа: {value}",
                f'список doc_type="{value}"',
            )
            if len(suggestions) >= limit:
                return suggestions

    # approval stages
    for value in lookups["approval_stages"]:
        if q in value.lower():
            _append_suggestion(
                suggestions,
                seen,
                "approval_stage",
                f"Текущая стадия согласования: {value}",
                f'список current_approval_stage="{value}"',
            )
            if len(suggestions) >= limit:
                return suggestions

    # intent-aware шаблоны
    if "дит" in q:
        _append_suggestion(
            suggestions,
            seen,
            "template",
            "Что ждёт согласования от ДИТ?",
            "Что ждёт согласования от ДИТ?",
        )

    if "гку" in q:
        _append_suggestion(
            suggestions,
            seen,
            "template",
            "Какие задачи ждут согласования от ГКУ?",
            "Какие задачи ждут согласования от ГКУ?",
        )

    if "срок" in q or "проср" in q or "дедлайн" in q:
        _append_suggestion(
            suggestions,
            seen,
            "template",
            "Какие задачи просрочены?",
            "Какие задачи просрочены?",
        )
        _append_suggestion(
            suggestions,
            seen,
            "template",
            "Какие сроки согласования истекают в ближайшие 7 дней?",
            "Какие сроки согласования истекают в ближайшие 7 дней?",
        )

    if "стат" in q or "анал" in q:
        _append_suggestion(
            suggestions,
            seen,
            "template",
            "Статистика по статусам",
            "Статистика по статусам",
        )
        _append_suggestion(
            suggestions,
            seen,
            "template",
            "Сколько задач у каждого заказчика?",
            "Сколько задач у каждого заказчика?",
        )

    return suggestions[:limit]


def _serialize_pending_approvals(value) -> str:
    if not isinstance(value, list):
        return ""
    return ", ".join(safe_str(x) for x in value if safe_str(x))


def _task_export_rows(tasks: list[dict]) -> list[dict]:
    rows = []

    for task in tasks:
        main_deadline = task.get("main_deadline", {}) if isinstance(task.get("main_deadline"), dict) else {}

        rows.append(
            {
                "issue_id": safe_str(task.get("issue_id")),
                "summary": safe_str(task.get("summary")),
                "status": safe_str(task.get("status")),
                "priority": safe_str(task.get("priority")),
                "doc_type": safe_str(task.get("doc_type")),
                "functional_customer": safe_str(task.get("functional_customer")),
                "responsible_dit": safe_str(task.get("responsible_dit")),
                "current_approval_stage": safe_str(task.get("current_approval_stage")),
                "is_active": bool(task.get("is_active")),
                "is_final": bool(task.get("is_final")),
                "is_overdue": bool(task.get("is_overdue")),
                "overdue_days": task.get("overdue_days", 0),
                "main_deadline_label": safe_str(main_deadline.get("label")),
                "main_deadline_value": safe_str(main_deadline.get("value")),
                "pending_approvals": _serialize_pending_approvals(task.get("pending_approvals")),
            }
        )

    return rows


def _item_export_rows(items: list) -> tuple[list[dict], list[str]]:
    """
    Экспорт результатов для modes вроде:
    - overdue
    - deadlines
    - stats / count
    """
    if not items:
        return [], []

    # overdue/deadlines/items как список словарей
    if isinstance(items[0], dict):
        rows = []
        fieldnames = set()

        for item in items:
            row = {}
            for key, value in item.items():
                if isinstance(value, list):
                    row[key] = ", ".join(safe_str(x) for x in value if safe_str(x))
                elif isinstance(value, dict):
                    row[key] = json.dumps(value, ensure_ascii=False)
                else:
                    row[key] = value
                fieldnames.add(key)
            rows.append(row)

        return rows, sorted(fieldnames)

    # count/stats как list[tuple[str, int]]
    if isinstance(items[0], (list, tuple)) and len(items[0]) >= 2:
        rows = [{"name": item[0], "count": item[1]} for item in items]
        return rows, ["name", "count"]

    return [], []


def _build_csv_bytes(rows: list[dict], fieldnames: list[str]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()

    for row in rows:
        writer.writerow(row)

    return buffer.getvalue().encode("utf-8-sig")


def export_results_action(query: str, mode: str) -> tuple[bytes, str]:
    """
    Экспортирует результат запроса в CSV.

    Логика:
    - если в ответе есть tasks -> экспортируем задачи
    - иначе если есть items -> экспортируем items
    - иначе даем минимальный CSV с short_answer
    """
    result = run_agent_web(query, mode)

    tasks = result.get("tasks", [])
    single_task = result.get("task")
    items = result.get("items", [])

    if single_task and not tasks:
        tasks = [single_task]

    if tasks:
        rows = _task_export_rows(tasks)
        fieldnames = list(rows[0].keys()) if rows else []
        filename = "agent_tasks_export.csv"
        return _build_csv_bytes(rows, fieldnames), filename

    if items:
        rows, fieldnames = _item_export_rows(items)
        filename = "agent_items_export.csv"
        return _build_csv_bytes(rows, fieldnames), filename

    rows = [{"short_answer": safe_str(result.get("short_answer"))}]
    return _build_csv_bytes(rows, ["short_answer"]), "agent_result_export.csv"


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