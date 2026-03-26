# answer_builder.py формирует единый структурированный формат ответа агента
# и отвечает за его человекочитаемое представление в CLI.


def task_card(task: dict) -> dict:
    issue_id = task.get("issue_id", "")
    summary = task.get("summary", "")

    return {
        "mode": "task_card",
        "short_answer": f"Найдена задача {issue_id}: {summary}",
        "evidence": [
            f"Статус: {task.get('status', '')}",
            f"Приоритет: {task.get('priority', '')}",
            f"Тип документа: {task.get('doc_type', '')}",
            f"Функциональный заказчик: {task.get('functional_customer', '')}",
            f"Ответственный (ДИТ): {task.get('responsible_dit', '')}",
        ],
        "limitations": [],
        "used_issue_ids": [issue_id] if issue_id else [],
        "task": task,
    }


def task_list(title: str, tasks: list[dict]) -> dict:
    short_answer = title if tasks else f"{title}. Совпадений не найдено."

    return {
        "mode": "task_list",
        "short_answer": short_answer,
        "evidence": [f"Найдено задач: {len(tasks)}"],
        "limitations": [],
        "used_issue_ids": [t.get("issue_id", "") for t in tasks if t.get("issue_id")],
        "tasks": tasks,
    }


def count_result(field: str, items: list[tuple[str, int]]) -> dict:
    short_answer = f"Сводка по полю {field}" if items else f"Нет данных для сводки по полю {field}"

    return {
        "mode": "count",
        "short_answer": short_answer,
        "evidence": [f"{name}: {count}" for name, count in items[:10]],
        "limitations": [],
        "used_issue_ids": [],
        "items": items,
    }


def deadlines_result(items: list[dict], days: int) -> dict:
    if items:
        short_answer = f"Найдено дедлайнов в ближайшие {days} дн.: {len(items)}"
    else:
        short_answer = f"В ближайшие {days} дн. дедлайнов не найдено."

    return {
        "mode": "deadlines",
        "short_answer": short_answer,
        "evidence": [
            f"{x.get('issue_id', '')} | {x.get('deadline_label', '')} | {x.get('deadline_value', '')}"
            for x in items[:10]
        ],
        "limitations": [],
        "used_issue_ids": [x.get("issue_id", "") for x in items if x.get("issue_id")],
        "items": items,
    }


def llm_result(parsed: dict, mode: str, tasks: list[dict]) -> dict:
    """
    Приводит parsed LLM-ответ к общей схеме ответа агента
    и защищает систему от галлюцинаций в used_issue_ids.
    """
    valid_ids = {t.get("issue_id", "") for t in tasks if t.get("issue_id")}

    used_issue_ids = parsed.get("used_issue_ids", [])
    if not isinstance(used_issue_ids, list):
        used_issue_ids = []

    # Оставляем только те ID, которые реально есть среди найденных задач.
    used_issue_ids = [x for x in used_issue_ids if x in valid_ids]

    # Если модель не вернула ни одного валидного ID, используем найденные задачи.
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
    }


def fallback_result(mode: str, tasks: list[dict], message: str, extra_limitations: list[str] | None = None) -> dict:
    """
    Возвращает детерминированный fallback-ответ, если LLM недоступна
    или вернула неверный формат.
    """
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
    }


def pretty_print_response(response: dict) -> str:
    lines = []

    used_llm = response.get("used_llm")
    if used_llm is True:
        lines.append("[через LLM]")
    elif used_llm is False:
        lines.append("[без LLM]")

    lines.append(response.get("short_answer", ""))

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
            lines.append(
                f" - {task.get('issue_id', '')} | {task.get('status', '')} | {task.get('priority', '')} | {task.get('summary', '')}"
            )

    return "\n".join(lines).strip()