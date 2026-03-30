from src.utils import safe_str


def _clean_filters(applied_filters: list[str] | None) -> list[str]:
    if not applied_filters:
        return []
    return [safe_str(x) for x in applied_filters if safe_str(x)]


def task_card(task: dict) -> dict:
    issue_id = task.get("issue_id", "")
    summary = task.get("summary", "")

    evidence = [
        f"Статус: {task.get('status', '')}",
        f"Приоритет: {task.get('priority', '')}",
        f"Тип документа: {task.get('doc_type', '')}",
        f"Функциональный заказчик: {task.get('functional_customer', '')}",
        f"Ответственный (ДИТ): {task.get('responsible_dit', '')}",
    ]

    main_deadline = task.get("main_deadline", {})
    if isinstance(main_deadline, dict) and safe_str(main_deadline.get("value")):
        evidence.append(
            f"Ближайший дедлайн: {safe_str(main_deadline.get('label'))} = {safe_str(main_deadline.get('value'))}"
        )

    current_stage = safe_str(task.get("current_approval_stage"))
    if current_stage:
        evidence.append(f"Текущая стадия согласования: {current_stage}")

    return {
        "mode": "task_card",
        "short_answer": f"Найдена задача {issue_id}: {summary}",
        "evidence": evidence,
        "limitations": [],
        "used_issue_ids": [issue_id] if issue_id else [],
        "task": task,
        "confidence": "high",
        "applied_filters": [],
    }


def task_list(
    title: str,
    tasks: list[dict],
    applied_filters: list[str] | None = None,
    limitations: list[str] | None = None,
    confidence: str = "high",
) -> dict:
    short_answer = title if tasks else f"{title}. Совпадений не найдено."

    evidence = [f"Найдено задач: {len(tasks)}"]
    applied_filters = _clean_filters(applied_filters)

    if applied_filters:
        evidence.append("Фильтры: " + "; ".join(applied_filters))

    return {
        "mode": "task_list",
        "short_answer": short_answer,
        "evidence": evidence,
        "limitations": limitations or [],
        "used_issue_ids": [t.get("issue_id", "") for t in tasks if t.get("issue_id")],
        "tasks": tasks,
        "confidence": confidence,
        "applied_filters": applied_filters,
    }


def count_result(
    field: str,
    items: list[tuple[str, int]],
    total_tasks: int = 0,
    applied_filters: list[str] | None = None,
    confidence: str = "high",
) -> dict:
    short_answer = (
        f"Сводка по полю {field}" if items else f"Нет данных для сводки по полю {field}"
    )

    evidence = []
    if total_tasks:
        evidence.append(f"Задач в выборке: {total_tasks}")

    evidence.extend([f"{name}: {count}" for name, count in items[:10]])

    applied_filters = _clean_filters(applied_filters)
    if applied_filters:
        evidence.append("Фильтры: " + "; ".join(applied_filters))

    return {
        "mode": "count",
        "short_answer": short_answer,
        "evidence": evidence,
        "limitations": [],
        "used_issue_ids": [],
        "items": items,
        "confidence": confidence,
        "applied_filters": applied_filters,
    }


def deadlines_result(
    items: list[dict],
    days: int,
    overdue_only: bool = False,
    active_only: bool = True,
    confidence: str = "high",
) -> dict:
    if overdue_only:
        short_answer = (
            f"Найдено просроченных дедлайнов: {len(items)}"
            if items
            else "Просроченных дедлайнов не найдено."
        )
    else:
        short_answer = (
            f"Найдено дедлайнов в ближайшие {days} дн.: {len(items)}"
            if items
            else f"В ближайшие {days} дн. дедлайнов не найдено."
        )

    evidence = []

    if active_only:
        evidence.append("Проверялись только активные задачи.")

    for x in items[:10]:
        base = f"{x.get('issue_id', '')} | {x.get('deadline_label', '')} | {x.get('deadline_value', '')}"
        if overdue_only and x.get("overdue_days"):
            base += f" | просрочка: {x.get('overdue_days')} дн."
        elif x.get("days_to_deadline") is not None:
            base += f" | осталось: {x.get('days_to_deadline')} дн."
        evidence.append(base)

    return {
        "mode": "deadlines",
        "short_answer": short_answer,
        "evidence": evidence,
        "limitations": [],
        "used_issue_ids": [x.get("issue_id", "") for x in items if x.get("issue_id")],
        "items": items,
        "confidence": confidence,
        "applied_filters": [],
    }


def approval_status_result(
    title: str,
    tasks: list[dict],
    department_label: str,
    approval_bucket: str | None = None,
    decision_missing: bool = False,
    applied_filters: list[str] | None = None,
    confidence: str = "high",
) -> dict:
    if decision_missing:
        short_answer = (
            f"Найдено задач без принятого решения {department_label}: {len(tasks)}"
            if tasks
            else f"Задач без принятого решения {department_label} не найдено."
        )
    elif approval_bucket == "pending":
        short_answer = (
            f"Найдено задач, ожидающих согласования от {department_label}: {len(tasks)}"
            if tasks
            else f"Задач, ожидающих согласования от {department_label}, не найдено."
        )
    elif approval_bucket == "negative":
        short_answer = (
            f"Найдено задач с отказом/отменой по {department_label}: {len(tasks)}"
            if tasks
            else f"Задач с отказом/отменой по {department_label} не найдено."
        )
    else:
        short_answer = title if tasks else f"{title}. Совпадений не найдено."

    evidence = [f"Найдено задач: {len(tasks)}"]
    applied_filters = _clean_filters(applied_filters)

    if applied_filters:
        evidence.append("Фильтры: " + "; ".join(applied_filters))

    for task in tasks[:10]:
        line = f"{task.get('issue_id', '')} | {task.get('status', '')} | {task.get('summary', '')}"
        current_stage = safe_str(task.get("current_approval_stage"))
        if current_stage:
            line += f" | стадия: {current_stage}"
        evidence.append(line)

    return {
        "mode": "approval_status",
        "short_answer": short_answer,
        "evidence": evidence,
        "limitations": [],
        "used_issue_ids": [t.get("issue_id", "") for t in tasks if t.get("issue_id")],
        "tasks": tasks,
        "confidence": confidence,
        "applied_filters": applied_filters,
    }


def overdue_result(
    items: list[dict],
    deadline_field: str | None = None,
    applied_filters: list[str] | None = None,
    confidence: str = "high",
) -> dict:
    short_answer = (
        f"Найдено просроченных задач: {len(items)}"
        if items
        else "Просроченных задач не найдено."
    )

    evidence = []
    applied_filters = _clean_filters(applied_filters)

    if deadline_field:
        evidence.append(f"Проверялся конкретный дедлайн: {deadline_field}")

    if applied_filters:
        evidence.append("Фильтры: " + "; ".join(applied_filters))

    for item in items[:10]:
        evidence.append(
            f"{item.get('issue_id', '')} | {item.get('deadline_label', '')} | {item.get('deadline_value', '')} | просрочка: {item.get('overdue_days', 0)} дн."
        )

    return {
        "mode": "overdue",
        "short_answer": short_answer,
        "evidence": evidence,
        "limitations": [],
        "used_issue_ids": [x.get("issue_id", "") for x in items if x.get("issue_id")],
        "items": items,
        "confidence": confidence,
        "applied_filters": applied_filters,
    }


def stats_result(
    title: str,
    grouped_items: list[tuple[str, int]],
    kpis: dict,
    group_field: str,
    total_tasks: int,
    applied_filters: list[str] | None = None,
    confidence: str = "high",
) -> dict:
    short_answer = title if grouped_items or total_tasks else "Нет данных для статистики."

    evidence = [
        f"Задач в выборке: {total_tasks}",
        f"Всего: {kpis.get('total', 0)}",
        f"Активных: {kpis.get('active', 0)}",
        f"Финальных: {kpis.get('final', 0)}",
        f"Просроченных: {kpis.get('overdue', 0)}",
        f"С замечаниями: {kpis.get('with_remarks', 0)}",
        f"С pending approvals: {kpis.get('pending_approvals', 0)}",
    ]

    applied_filters = _clean_filters(applied_filters)
    if applied_filters:
        evidence.append("Фильтры: " + "; ".join(applied_filters))

    for name, count in grouped_items[:10]:
        evidence.append(f"{group_field}: {name} = {count}")

    return {
        "mode": "stats",
        "short_answer": short_answer,
        "evidence": evidence,
        "limitations": [],
        "used_issue_ids": [],
        "items": grouped_items,
        "confidence": confidence,
        "applied_filters": applied_filters,
    }


def llm_result(parsed: dict, mode: str, tasks: list[dict]) -> dict:
    valid_ids = {t.get("issue_id", "") for t in tasks if t.get("issue_id")}

    used_issue_ids = parsed.get("used_issue_ids", [])
    if not isinstance(used_issue_ids, list):
        used_issue_ids = []

    used_issue_ids = [x for x in used_issue_ids if x in valid_ids]

    if not used_issue_ids:
        used_issue_ids = list(valid_ids)

    evidence = parsed.get("evidence", [])
    limitations = parsed.get("limitations", [])

    if not isinstance(evidence, list):
        evidence = []

    if not isinstance(limitations, list):
        limitations = []

    return {
        "mode": mode,
        "short_answer": str(parsed.get("short_answer", "")).strip(),
        "evidence": evidence,
        "limitations": limitations,
        "used_issue_ids": used_issue_ids,
        "tasks": tasks,
        "confidence": "medium",
        "applied_filters": [],
    }


def fallback_result(
    mode: str,
    tasks: list[dict],
    message: str,
    extra_limitations: list[str] | None = None,
) -> dict:
    if tasks:
        evidence = [
            f"{task.get('issue_id', '')}: {task.get('summary', '')} | {task.get('status', '')}"
            for task in tasks[:10]
        ]
    else:
        evidence = ["Релевантные задачи не найдены."]

    limitations = [
        "LLM недоступна или вернула неверный формат, поэтому показан детерминированный ответ."
    ]

    if extra_limitations:
        limitations.extend(extra_limitations)

    return {
        "mode": mode,
        "short_answer": message,
        "evidence": evidence,
        "limitations": limitations,
        "used_issue_ids": [t.get("issue_id", "") for t in tasks if t.get("issue_id")],
        "tasks": tasks,
        "confidence": "low",
        "applied_filters": [],
    }


def pretty_print_response(response: dict) -> str:
    lines = []

    used_llm = response.get("used_llm")
    if used_llm is True:
        lines.append("[через LLM]")
    elif used_llm is False:
        lines.append("[без LLM]")

    confidence = safe_str(response.get("confidence"))
    if confidence:
        lines.append(f"Уверенность: {confidence}")

    lines.append(response.get("short_answer", ""))

    applied_filters = response.get("applied_filters", [])
    if applied_filters:
        lines.append("\nПримененные фильтры:")
        for item in applied_filters:
            lines.append(f" - {item}")

    evidence = response.get("evidence", [])
    if evidence:
        lines.append("\nОснование:")
        for item in evidence:
            lines.append(f" - {item}")

    limitations = response.get("limitations", [])
    if limitations:
        lines.append("\nОграничения:")
        for item in limitations:
            lines.append(f" - {item}")

    used_ids = response.get("used_issue_ids", [])
    if used_ids:
        lines.append("\nИспользованные задачи:")
        for iid in used_ids:
            lines.append(f" - {iid}")

    tasks = response.get("tasks", [])
    single_task = response.get("task")
    if single_task and not tasks:
        tasks = [single_task]

    if tasks:
        lines.append("\nНайденные задачи:")
        for task in tasks[:10]:
            line = (
                f" - {task.get('issue_id', '')} | "
                f"{task.get('status', '')} | "
                f"{task.get('priority', '')} | "
                f"{task.get('summary', '')}"
            )
            current_stage = safe_str(task.get("current_approval_stage"))
            if current_stage:
                line += f" | стадия: {current_stage}"
            lines.append(line)

    items = response.get("items", [])
    if items and response.get("mode") in {"overdue", "deadlines"}:
        lines.append("\nДетали:")
        for item in items[:10]:
            if response.get("mode") == "overdue":
                lines.append(
                    f" - {item.get('issue_id', '')} | {item.get('deadline_label', '')} | {item.get('deadline_value', '')} | просрочка: {item.get('overdue_days', 0)} дн."
                )
            else:
                base = f" - {item.get('issue_id', '')} | {item.get('deadline_label', '')} | {item.get('deadline_value', '')}"
                if item.get("days_to_deadline") is not None:
                    base += f" | осталось: {item.get('days_to_deadline')} дн."
                lines.append(base)

    return "\n".join(lines).strip()