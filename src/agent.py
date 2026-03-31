import json
from time import perf_counter

from src.config import DEEP_ANALYSIS_TOP_K, FAST_ANALYSIS_TOP_K, USE_CRITIC_PASS
from src.query_parser import detect_intent
from src.search_engine import (
    aggregate_counts,
    exact_search,
    filter_tasks,
    find_overdue_entries,
    find_related_tasks,
    find_task_by_id,
    find_tasks_by_approval,
    find_tasks_with_remarks,
    hybrid_search,
    upcoming_deadlines,
)
from src.prompts import build_critic_prompt, build_llm_prompt
from src.ollama_client import ollama_client
from src.response_parser import parse_json_safely, validate_llm_result
from src.answer_builder import (
    approval_status_result,
    count_result,
    deadlines_result,
    fallback_result,
    llm_result,
    overdue_result,
    stats_result,
    task_card,
    task_list,
)
from src.history_store import save_history
from src.utils import safe_str


# Modes where LLM synthesis genuinely adds value (retrieval-first, then LLM).
# Deterministic modes (list, count, deadlines, stats, overdue, approval_status,
# by_customer, by_responsible, with_remarks) must NOT use LLM in auto mode.
LLM_SYNTHESIS_MODES = {
    "similar",
    "analyze_new_task",
    "general_search",
}

EXPLICIT_DEEP_PREFIXES = ("глубоко ", "deep ")


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen = set()
    result = []

    for item in items:
        item = safe_str(item)
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)

    return result


def _extract_analysis_profile(user_query: str) -> tuple[str, str]:
    """
    Возвращает:
    - очищенный запрос
    - analysis_profile: fast | deep

    deep включается:
    - по префиксу "глубоко " / "deep "
    - по словам "подробно", "детально", "глубокий анализ"
    """
    query = safe_str(user_query)
    lower = query.lower().strip()

    for prefix in EXPLICIT_DEEP_PREFIXES:
        if lower.startswith(prefix):
            cleaned = query[len(prefix):].strip()
            return cleaned or query, "deep"

    deep_markers = [
        "глубокий анализ",
        "детально",
        "подробно",
        "максимально подробно",
    ]
    if any(marker in lower for marker in deep_markers):
        return query, "deep"

    return query, "fast"


def _top_k_for_profile(analysis_profile: str) -> int:
    return DEEP_ANALYSIS_TOP_K if analysis_profile == "deep" else FAST_ANALYSIS_TOP_K


def _dataset_kpis(tasks: list[dict]) -> dict:
    total = len(tasks)
    active = sum(1 for t in tasks if t.get("is_active"))
    final = sum(1 for t in tasks if t.get("is_final"))
    overdue = sum(1 for t in tasks if t.get("is_overdue"))
    with_remarks = sum(
        1 for t in tasks
        if "замеч" in safe_str(t.get("status")).lower()
        or "замеч" in safe_str(t.get("raw_status")).lower()
    )
    pending = sum(1 for t in tasks if t.get("pending_approvals"))

    return {
        "total": total,
        "active": active,
        "final": final,
        "overdue": overdue,
        "with_remarks": with_remarks,
        "pending_approvals": pending,
    }


def _tasks_from_issue_ids(issue_ids: list[str]) -> list[dict]:
    result = []

    for issue_id in _dedupe_keep_order(issue_ids):
        task = find_task_by_id(issue_id)
        if task is not None:
            result.append(task)

    return result


def _build_applied_filters(intent: dict) -> list[str]:
    filters = intent.get("filters", {})
    lines = []

    for key in [
        "status",
        "raw_status",
        "status_group",
        "workflow_group",
        "priority",
        "doc_type",
        "functional_customer",
        "responsible_dit",
        "current_approval_stage",
    ]:
        value = safe_str(filters.get(key))
        if value:
            lines.append(f"{key}={value}")

    if safe_str(intent.get("approval_field")):
        lines.append(f"approval_field={safe_str(intent.get('approval_field'))}")

    if safe_str(intent.get("approval_bucket")):
        lines.append(f"approval_bucket={safe_str(intent.get('approval_bucket'))}")

    if safe_str(intent.get("deadline_field")):
        lines.append(f"deadline_field={safe_str(intent.get('deadline_field'))}")

    if intent.get("decision_missing") is True:
        lines.append("без принятого решения")

    if intent.get("active_only") is True:
        lines.append("только активные")

    if intent.get("final_only") is True:
        lines.append("только финальные")

    if intent.get("overdue_only") is True:
        lines.append("только просроченные дедлайны")

    return lines


def _list_title(intent: dict) -> str:
    if intent.get("overdue_only"):
        return "Просроченные задачи"

    filters = intent.get("filters", {})

    if filters.get("status") == "Направлено на согл.":
        return "Задачи на согласовании"

    if intent.get("active_only") is True and not filters:
        return "Активные задачи"

    if intent.get("final_only") is True and not filters:
        return "Финальные задачи"

    return "Список задач по фильтрам"


def _build_stats_title(field: str) -> str:
    titles = {
        "status": "Статистика по статусам",
        "workflow_group": "Статистика по workflow-группам",
        "priority": "Статистика по приоритетам",
        "doc_type": "Статистика по типам документов",
        "functional_customer": "Статистика по функциональным заказчикам",
        "responsible_dit": "Статистика по ответственным",
        "current_approval_stage": "Статистика по текущим стадиям согласования",
    }
    return titles.get(field, f"Статистика по полю {field}")


def _apply_filters(intent: dict) -> list[dict]:
    filters = intent.get("filters", {})

    return filter_tasks(
        status=filters.get("status"),
        raw_status=filters.get("raw_status"),
        status_group=filters.get("status_group"),
        workflow_group=filters.get("workflow_group"),
        priority=filters.get("priority"),
        doc_type=filters.get("doc_type"),
        functional_customer=filters.get("functional_customer"),
        responsible_dit=filters.get("responsible_dit"),
        current_approval_stage=filters.get("current_approval_stage"),
        active_only=intent.get("active_only"),
        final_only=intent.get("final_only"),
        overdue_only=bool(intent.get("overdue_only", False)),
    )


def _build_grouped_context(field: str, items: list[tuple[str, int]]) -> str:
    if not items:
        return "Агрегатов нет."

    lines = [f"Агрегаты по полю {field}:"]
    for name, count in items[:12]:
        lines.append(f"- {name}: {count}")
    return "\n".join(lines)


def _build_overdue_context(items: list[dict]) -> str:
    if not items:
        return "Просроченных элементов нет."

    lines = ["Ключевые просроченные сроки:"]
    for item in items[:12]:
        lines.append(
            f"- {safe_str(item.get('issue_id'))} | "
            f"{safe_str(item.get('deadline_label'))} | "
            f"{safe_str(item.get('deadline_value'))} | "
            f"просрочка: {safe_str(item.get('overdue_days'))} дн."
        )
    return "\n".join(lines)


def _build_deadline_context(items: list[dict]) -> str:
    if not items:
        return "Ближайших сроков нет."

    lines = ["Ключевые ближайшие сроки:"]
    for item in items[:12]:
        suffix = ""
        if item.get("days_to_deadline") is not None:
            suffix = f" | осталось: {item.get('days_to_deadline')} дн."
        lines.append(
            f"- {safe_str(item.get('issue_id'))} | "
            f"{safe_str(item.get('deadline_label'))} | "
            f"{safe_str(item.get('deadline_value'))}{suffix}"
        )
    return "\n".join(lines)


def _build_task_sample_context(tasks: list[dict]) -> str:
    if not tasks:
        return "Задач в выборке нет."

    lines = ["Краткая сводка по выборке:"]
    for task in tasks[:10]:
        lines.append(
            f"- {safe_str(task.get('issue_id'))} | "
            f"{safe_str(task.get('status'))} | "
            f"{safe_str(task.get('priority'))} | "
            f"{safe_str(task.get('current_approval_stage'))} | "
            f"{safe_str(task.get('summary'))}"
        )
    return "\n".join(lines)


def _build_extra_context(
    mode: str,
    intent: dict,
    tasks: list[dict] | None = None,
    items: list | None = None,
    grouped_items: list[tuple[str, int]] | None = None,
) -> str:
    tasks = tasks or []
    items = items or []
    grouped_items = grouped_items or []

    parts = []

    if tasks:
        kpis = _dataset_kpis(tasks)
        parts.append(
            "\n".join([
                "KPI по текущей выборке:",
                f"- total: {kpis['total']}",
                f"- active: {kpis['active']}",
                f"- final: {kpis['final']}",
                f"- overdue: {kpis['overdue']}",
                f"- with_remarks: {kpis['with_remarks']}",
                f"- pending_approvals: {kpis['pending_approvals']}",
            ])
        )
        parts.append(_build_task_sample_context(tasks))

    if mode in {"stats", "count"} and grouped_items:
        field = safe_str(intent.get("field"))
        parts.append(_build_grouped_context(field, grouped_items))

    if mode == "overdue" and items:
        parts.append(_build_overdue_context(items))

    if mode == "deadlines" and items:
        parts.append(_build_deadline_context(items))

    if mode == "approval_status":
        department_label = safe_str(intent.get("department_label"))
        approval_bucket = safe_str(intent.get("approval_bucket"))
        decision_missing = bool(intent.get("decision_missing"))

        lines = ["Контекст режима согласований:"]
        if department_label:
            lines.append(f"- ведомство: {department_label}")
        if approval_bucket:
            lines.append(f"- искомый bucket: {approval_bucket}")
        if decision_missing:
            lines.append("- фокус: задачи без принятого решения")
        parts.append("\n".join(lines))

    if not parts:
        return "Дополнительной агрегированной аналитики нет."

    return "\n\n".join(parts)


def _merge_llm_with_base(base_result: dict, llm_response: dict, analysis_profile: str) -> dict:
    merged = dict(base_result)

    merged["short_answer"] = llm_response.get("short_answer", base_result.get("short_answer", ""))
    merged["evidence"] = llm_response.get("evidence", base_result.get("evidence", []))

    base_limitations = base_result.get("limitations", [])
    llm_limitations = llm_response.get("limitations", [])
    merged["limitations"] = _dedupe_keep_order(
        [*base_limitations, *llm_limitations]
    )

    merged["used_issue_ids"] = llm_response.get("used_issue_ids", base_result.get("used_issue_ids", []))
    merged["used_llm"] = True
    merged["analysis_profile"] = analysis_profile

    if llm_response.get("confidence"):
        merged["confidence"] = llm_response["confidence"]

    return merged


def _run_two_pass_llm(
    user_query: str,
    mode: str,
    tasks: list[dict],
    analysis_profile: str,
    fallback_message: str,
    extra_context: str = "",
) -> dict:
    """
    2-pass pipeline:
    1. analyst pass — делает полезный grounded draft
    2. critic pass  — срезает неподтвержденные формулировки

    Если critic не сработал, используем analyst result.
    """
    if not tasks:
        result = fallback_result(
            mode,
            [],
            "Подходящие задачи не найдены.",
            extra_limitations=["Для аналитического ответа не найдено релевантных задач."],
        )
        result["used_llm"] = False
        result["analysis_profile"] = analysis_profile
        return result

    analyst_prompt = build_llm_prompt(
        user_query=user_query,
        tasks=tasks,
        mode=mode,
        analysis_profile=analysis_profile,
        extra_context=extra_context,
    )

    try:
        analyst_raw = ollama_client.generate(analyst_prompt)
        analyst_parsed = parse_json_safely(analyst_raw)
        analyst_parsed = validate_llm_result(analyst_parsed, tasks)
    except Exception as e:
        result = fallback_result(
            mode,
            tasks,
            fallback_message,
            extra_limitations=[f"Analyst pass не сработал: {e}"],
        )
        result["used_llm"] = False
        result["analysis_profile"] = analysis_profile
        return result

    critic_failed_reason = ""

    if USE_CRITIC_PASS:
        try:
            critic_prompt = build_critic_prompt(
                user_query=user_query,
                tasks=tasks,
                mode=mode,
                draft_result=analyst_parsed,
                analysis_profile=analysis_profile,
                extra_context=extra_context,
            )
            critic_raw = ollama_client.generate(critic_prompt)
            critic_parsed = parse_json_safely(critic_raw)
            critic_parsed = validate_llm_result(critic_parsed, tasks)
            final_parsed = critic_parsed
        except Exception as e:
            critic_failed_reason = str(e)
            final_parsed = analyst_parsed
    else:
        final_parsed = analyst_parsed

    result = llm_result(final_parsed, mode, tasks)
    result["used_llm"] = True
    result["analysis_profile"] = analysis_profile

    if critic_failed_reason:
        limitations = result.get("limitations", [])
        limitations.append(
            f"Critic pass не сработал, использован analyst pass: {critic_failed_reason}"
        )
        result["limitations"] = _dedupe_keep_order(limitations)

    return result


def _should_use_llm(mode: str, analysis_profile: str) -> bool:
    if analysis_profile == "deep":
        return True
    return mode in LLM_SYNTHESIS_MODES


def run_agent(user_query: str) -> dict:
    started = perf_counter()
    error_text = ""
    llm_used = 0
    retrieved_candidates = []

    cleaned_query, analysis_profile = _extract_analysis_profile(user_query)
    intent = detect_intent(cleaned_query)
    mode = intent["mode"]

    if mode == "help":
        result = {
            "mode": "help",
            "short_answer": (
                "Можно писать свободным текстом: "
                "'Что ждёт согласования от ДИТ?', "
                "'Какие задачи просрочены?', "
                "'Статистика по статусам', "
                "'Задачи где ответственный SAA_1', "
                "'Похожие уведомления', "
                "'Проанализируй новую задачу ...'. "
                "Для глубокого LLM-анализа начни запрос со слова 'глубоко'."
            ),
            "evidence": [],
            "limitations": [],
            "used_issue_ids": [],
            "used_llm": False,
            "confidence": "high",
            "applied_filters": [],
            "analysis_profile": analysis_profile,
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

        result["duration_ms"] = int((perf_counter() - started) * 1000)
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
                    "confidence": "high",
                    "applied_filters": [],
                    "analysis_profile": analysis_profile,
                }
            else:
                base_result = task_card(task)
                related = find_related_tasks(task, limit=3)
                base_result["used_llm"] = False
                base_result["analysis_profile"] = analysis_profile

                if related:
                    base_result["tasks"] = [task] + related
                    base_result["used_issue_ids"] = [t["issue_id"] for t in [task] + related]
                    base_result["evidence"].append(
                        "Добавлены логически близкие задачи по совпадению текста и метаданных."
                    )

                if analysis_profile == "deep":
                    tasks_for_llm = [task] + related
                    llm_response = _run_two_pass_llm(
                        user_query=cleaned_query,
                        mode="task_by_id",
                        tasks=tasks_for_llm[:_top_k_for_profile(analysis_profile)],
                        analysis_profile=analysis_profile,
                        fallback_message=f"Показана задача {intent['issue_id']} и близкие задачи.",
                        extra_context=(
                            f"Главная задача: {task.get('issue_id', '')}. "
                            "Сфокусируй short_answer на ней, а related tasks используй как контекст."
                        ),
                    )
                    result = _merge_llm_with_base(base_result, llm_response, analysis_profile)
                else:
                    result = base_result

        elif mode == "approval_status":
            filters = intent.get("filters", {})

            tasks = find_tasks_by_approval(
                approval_field=intent["approval_field"],
                approval_bucket=intent.get("approval_bucket"),
                decision_field=intent.get("decision_field"),
                decision_missing=bool(intent.get("decision_missing", False)),
                status=filters.get("status"),
                raw_status=filters.get("raw_status"),
                status_group=filters.get("status_group"),
                workflow_group=filters.get("workflow_group"),
                priority=filters.get("priority"),
                doc_type=filters.get("doc_type"),
                functional_customer=filters.get("functional_customer"),
                responsible_dit=filters.get("responsible_dit"),
                active_only=intent.get("active_only"),
                final_only=intent.get("final_only"),
                limit=60,
            )
            retrieved_candidates = [t["issue_id"] for t in tasks]

            base_result = approval_status_result(
                title=f"Статус согласования по {intent.get('department_label', '')}",
                tasks=tasks[:30],
                department_label=intent.get("department_label", ""),
                approval_bucket=intent.get("approval_bucket"),
                decision_missing=bool(intent.get("decision_missing", False)),
                applied_filters=_build_applied_filters(intent),
                confidence="high",
            )
            base_result["used_llm"] = False
            base_result["analysis_profile"] = analysis_profile

            if len(tasks) > 30:
                base_result["limitations"].append("Показаны первые 30 задач.")

            if _should_use_llm(mode, analysis_profile):
                tasks_for_llm = tasks[:_top_k_for_profile(analysis_profile)]
                llm_response = _run_two_pass_llm(
                    user_query=cleaned_query,
                    mode=mode,
                    tasks=tasks_for_llm,
                    analysis_profile=analysis_profile,
                    fallback_message="Показаны задачи по статусу согласования.",
                    extra_context=_build_extra_context(mode, intent, tasks=tasks, items=[]),
                )
                result = _merge_llm_with_base(base_result, llm_response, analysis_profile)
            else:
                result = base_result

        elif mode == "overdue":
            filters = intent.get("filters", {})

            items = find_overdue_entries(
                deadline_field=intent.get("deadline_field"),
                status=filters.get("status"),
                raw_status=filters.get("raw_status"),
                status_group=filters.get("status_group"),
                workflow_group=filters.get("workflow_group"),
                priority=filters.get("priority"),
                doc_type=filters.get("doc_type"),
                functional_customer=filters.get("functional_customer"),
                responsible_dit=filters.get("responsible_dit"),
                active_only=True if intent.get("active_only") is None else bool(intent.get("active_only")),
                final_only=intent.get("final_only"),
                limit=100,
            )
            retrieved_candidates = [x["issue_id"] for x in items]

            base_result = overdue_result(
                items=items[:50],
                deadline_field=intent.get("deadline_field"),
                applied_filters=_build_applied_filters(intent),
                confidence="high",
            )
            base_result["used_llm"] = False
            base_result["analysis_profile"] = analysis_profile

            if len(items) > 50:
                base_result["limitations"].append("Показаны первые 50 просроченных задач.")

            if _should_use_llm(mode, analysis_profile):
                tasks_for_llm = _tasks_from_issue_ids([x["issue_id"] for x in items])[:_top_k_for_profile(analysis_profile)]
                llm_response = _run_two_pass_llm(
                    user_query=cleaned_query,
                    mode=mode,
                    tasks=tasks_for_llm,
                    analysis_profile=analysis_profile,
                    fallback_message="Показаны просроченные задачи и сроки.",
                    extra_context=_build_extra_context(mode, intent, tasks=tasks_for_llm, items=items),
                )
                result = _merge_llm_with_base(base_result, llm_response, analysis_profile)
            else:
                result = base_result

        elif mode == "stats":
            tasks = _apply_filters(intent)
            retrieved_candidates = [t["issue_id"] for t in tasks]

            field = intent.get("field", "status")
            grouped = aggregate_counts(field, tasks)

            base_result = stats_result(
                title=_build_stats_title(field),
                grouped_items=grouped,
                kpis=_dataset_kpis(tasks),
                group_field=field,
                total_tasks=len(tasks),
                applied_filters=_build_applied_filters(intent),
                confidence="high",
            )
            base_result["used_llm"] = False
            base_result["analysis_profile"] = analysis_profile

            if _should_use_llm(mode, analysis_profile):
                tasks_for_llm = tasks[:_top_k_for_profile(analysis_profile)]
                llm_response = _run_two_pass_llm(
                    user_query=cleaned_query,
                    mode=mode,
                    tasks=tasks_for_llm,
                    analysis_profile=analysis_profile,
                    fallback_message="Показана статистика по найденной выборке.",
                    extra_context=_build_extra_context(mode, intent, tasks=tasks, grouped_items=grouped),
                )
                result = _merge_llm_with_base(base_result, llm_response, analysis_profile)
            else:
                result = base_result

        elif mode == "by_customer":
            tasks = _apply_filters(intent)
            retrieved_candidates = [t["issue_id"] for t in tasks]

            customer = safe_str(intent.get("filters", {}).get("functional_customer"))
            title = f"Задачи по заказчику {customer}" if customer else "Задачи по функциональному заказчику"

            base_result = task_list(
                title,
                tasks[:30],
                applied_filters=_build_applied_filters(intent),
                confidence="high",
            )
            base_result["used_llm"] = False
            base_result["analysis_profile"] = analysis_profile

            if len(tasks) > 30:
                base_result["limitations"].append("Показаны первые 30 задач.")

            if _should_use_llm(mode, analysis_profile):
                tasks_for_llm = tasks[:_top_k_for_profile(analysis_profile)]
                llm_response = _run_two_pass_llm(
                    user_query=cleaned_query,
                    mode=mode,
                    tasks=tasks_for_llm,
                    analysis_profile=analysis_profile,
                    fallback_message="Показаны задачи по заказчику.",
                    extra_context=_build_extra_context(mode, intent, tasks=tasks),
                )
                result = _merge_llm_with_base(base_result, llm_response, analysis_profile)
            else:
                result = base_result

        elif mode == "by_responsible":
            tasks = _apply_filters(intent)
            retrieved_candidates = [t["issue_id"] for t in tasks]

            responsible = safe_str(intent.get("filters", {}).get("responsible_dit"))
            title = f"Задачи по ответственному {responsible}" if responsible else "Задачи по ответственному"

            base_result = task_list(
                title,
                tasks[:30],
                applied_filters=_build_applied_filters(intent),
                confidence="high",
            )
            base_result["used_llm"] = False
            base_result["analysis_profile"] = analysis_profile

            if len(tasks) > 30:
                base_result["limitations"].append("Показаны первые 30 задач.")

            if _should_use_llm(mode, analysis_profile):
                tasks_for_llm = tasks[:_top_k_for_profile(analysis_profile)]
                llm_response = _run_two_pass_llm(
                    user_query=cleaned_query,
                    mode=mode,
                    tasks=tasks_for_llm,
                    analysis_profile=analysis_profile,
                    fallback_message="Показаны задачи по ответственному.",
                    extra_context=_build_extra_context(mode, intent, tasks=tasks),
                )
                result = _merge_llm_with_base(base_result, llm_response, analysis_profile)
            else:
                result = base_result

        elif mode == "with_remarks":
            filters = intent.get("filters", {})

            tasks = find_tasks_with_remarks(
                status=filters.get("status"),
                raw_status=filters.get("raw_status"),
                status_group=filters.get("status_group"),
                workflow_group=filters.get("workflow_group"),
                priority=filters.get("priority"),
                doc_type=filters.get("doc_type"),
                functional_customer=filters.get("functional_customer"),
                responsible_dit=filters.get("responsible_dit"),
                active_only=intent.get("active_only"),
                final_only=intent.get("final_only"),
                limit=60,
            )
            retrieved_candidates = [t["issue_id"] for t in tasks]

            base_result = task_list(
                "Задачи с замечаниями",
                tasks[:30],
                applied_filters=_build_applied_filters(intent),
                confidence="high",
            )
            base_result["used_llm"] = False
            base_result["analysis_profile"] = analysis_profile

            if len(tasks) > 30:
                base_result["limitations"].append("Показаны первые 30 задач.")

            if _should_use_llm(mode, analysis_profile):
                tasks_for_llm = tasks[:_top_k_for_profile(analysis_profile)]
                llm_response = _run_two_pass_llm(
                    user_query=cleaned_query,
                    mode=mode,
                    tasks=tasks_for_llm,
                    analysis_profile=analysis_profile,
                    fallback_message="Показаны задачи с замечаниями.",
                    extra_context=_build_extra_context(mode, intent, tasks=tasks),
                )
                result = _merge_llm_with_base(base_result, llm_response, analysis_profile)
            else:
                result = base_result

        elif mode == "list":
            tasks = _apply_filters(intent)
            retrieved_candidates = [t["issue_id"] for t in tasks]

            base_result = task_list(
                _list_title(intent),
                tasks[:30],
                applied_filters=_build_applied_filters(intent),
                confidence="high",
            )
            base_result["used_llm"] = False
            base_result["analysis_profile"] = analysis_profile

            if len(tasks) > 30:
                base_result["limitations"].append("Показаны первые 30 задач.")

            if _should_use_llm(mode, analysis_profile):
                tasks_for_llm = tasks[:_top_k_for_profile(analysis_profile)]
                llm_response = _run_two_pass_llm(
                    user_query=cleaned_query,
                    mode=mode,
                    tasks=tasks_for_llm,
                    analysis_profile=analysis_profile,
                    fallback_message="Показаны задачи по фильтрам.",
                    extra_context=_build_extra_context(mode, intent, tasks=tasks),
                )
                result = _merge_llm_with_base(base_result, llm_response, analysis_profile)
            else:
                result = base_result

        elif mode == "count":
            tasks = _apply_filters(intent)
            retrieved_candidates = [t["issue_id"] for t in tasks]
            items = aggregate_counts(intent["field"], tasks)

            base_result = count_result(
                intent["field"],
                items,
                total_tasks=len(tasks),
                applied_filters=_build_applied_filters(intent),
                confidence="high",
            )
            base_result["used_llm"] = False
            base_result["analysis_profile"] = analysis_profile

            if _should_use_llm(mode, analysis_profile):
                tasks_for_llm = tasks[:_top_k_for_profile(analysis_profile)]
                llm_response = _run_two_pass_llm(
                    user_query=cleaned_query,
                    mode=mode,
                    tasks=tasks_for_llm,
                    analysis_profile=analysis_profile,
                    fallback_message="Показана сводка по выборке.",
                    extra_context=_build_extra_context(mode, intent, tasks=tasks, grouped_items=items),
                )
                result = _merge_llm_with_base(base_result, llm_response, analysis_profile)
            else:
                result = base_result

        elif mode == "deadlines":
            items = upcoming_deadlines(
                days=intent["days"],
                overdue_only=bool(intent.get("overdue_only", False)),
                active_only=True if intent.get("active_only") is None else bool(intent.get("active_only")),
            )
            retrieved_candidates = [x["issue_id"] for x in items]

            base_result = deadlines_result(
                items,
                intent["days"],
                overdue_only=bool(intent.get("overdue_only", False)),
                active_only=True if intent.get("active_only") is None else bool(intent.get("active_only")),
                confidence="high",
            )
            base_result["used_llm"] = False
            base_result["analysis_profile"] = analysis_profile

            if _should_use_llm(mode, analysis_profile):
                tasks_for_llm = _tasks_from_issue_ids([x["issue_id"] for x in items])[:_top_k_for_profile(analysis_profile)]
                llm_response = _run_two_pass_llm(
                    user_query=cleaned_query,
                    mode=mode,
                    tasks=tasks_for_llm,
                    analysis_profile=analysis_profile,
                    fallback_message="Показаны ближайшие сроки.",
                    extra_context=_build_extra_context(mode, intent, tasks=tasks_for_llm, items=items),
                )
                result = _merge_llm_with_base(base_result, llm_response, analysis_profile)
            else:
                result = base_result

        elif mode == "exact_search":
            tasks = exact_search(intent["query"], top_k=10)
            retrieved_candidates = [t["issue_id"] for t in tasks]

            result = task_list(
                "Точный детерминированный поиск",
                tasks,
                applied_filters=[],
                confidence="high",
            )
            result["limitations"].append("LLM не использовалась.")
            result["used_llm"] = False
            result["analysis_profile"] = analysis_profile

        elif mode == "similar":
            tasks = hybrid_search(intent["query"], top_k=_top_k_for_profile(analysis_profile))
            retrieved_candidates = [t["issue_id"] for t in tasks]

            result = _run_two_pass_llm(
                user_query=cleaned_query,
                mode=mode,
                tasks=tasks,
                analysis_profile=analysis_profile,
                fallback_message="Показаны наиболее похожие задачи по retrieval.",
                extra_context=_build_extra_context(mode, intent, tasks=tasks),
            )

        elif mode == "analyze_new_task":
            tasks = hybrid_search(intent["query"], top_k=_top_k_for_profile(analysis_profile))
            retrieved_candidates = [t["issue_id"] for t in tasks]

            result = _run_two_pass_llm(
                user_query=cleaned_query,
                mode=mode,
                tasks=tasks,
                analysis_profile=analysis_profile,
                fallback_message="Показаны ближайшие аналоги для новой формулировки.",
                extra_context=_build_extra_context(mode, intent, tasks=tasks),
            )

        else:
            search_query = intent.get("query", cleaned_query)
            tasks = hybrid_search(search_query, top_k=_top_k_for_profile(analysis_profile))
            retrieved_candidates = [t["issue_id"] for t in tasks]

            if _should_use_llm(mode, analysis_profile):
                result = _run_two_pass_llm(
                    user_query=cleaned_query,
                    mode=mode,
                    tasks=tasks,
                    analysis_profile=analysis_profile,
                    fallback_message="Показаны ближайшие задачи по свободному запросу.",
                    extra_context=_build_extra_context(mode, intent, tasks=tasks),
                )
            else:
                result = task_list(
                    "Ближайшие задачи по запросу",
                    tasks,
                    applied_filters=[],
                    confidence="medium",
                )
                result["used_llm"] = False
                result["analysis_profile"] = analysis_profile

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
        result["analysis_profile"] = analysis_profile
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

    result["duration_ms"] = duration_ms
    return result