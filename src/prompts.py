from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None

from src.config import (
    MAX_CONTEXT_TASKS_FAST,
    MAX_CONTEXT_TASKS_DEEP,
    MAX_TEXT_CHARS_FAST,
    MAX_TEXT_CHARS_DEEP,
)
from src.utils import safe_str, truncate


def _moscow_now() -> datetime:
    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo("Europe/Moscow"))
        except Exception:
            pass
    return datetime.now()


def _now_label() -> str:
    return _moscow_now().strftime("%d.%m.%Y %H:%M")


def _today_label() -> str:
    return _moscow_now().strftime("%d.%m.%Y")


def _profile_limits(analysis_profile: str) -> tuple[int, int]:
    if analysis_profile == "deep":
        return MAX_CONTEXT_TASKS_DEEP, MAX_TEXT_CHARS_DEEP
    return MAX_CONTEXT_TASKS_FAST, MAX_TEXT_CHARS_FAST


SYSTEM_PROMPT = """Ты — локальный аналитический агент по задачам YouTrack.

Твоя задача — давать полезный, содержательный и аналитический ответ,
но только на основании переданных задач и их полей.

Строгие правила:
1. Используй только переданный контекст.
2. Не придумывай причины, решения, сроки, статусы, риски и выводы, которых нет в данных.
3. Если делаешь общий вывод по нескольким задачам, он должен реально следовать из контекста.
4. Если данных недостаточно — прямо укажи это в limitations.
5. used_issue_ids можно брать только из реально переданных задач.
6. Никогда не добавляй ID, которых нет в контексте.
7. Если похожесть или вывод слабые — скажи об этом прямо.
8. Не пиши markdown, не пиши пояснения до или после JSON.
9. Верни только один JSON-объект.

Формат ответа — только JSON:
{
  "short_answer": "краткий, но полезный аналитический вывод",
  "evidence": [
    "факт 1",
    "факт 2"
  ],
  "limitations": [
    "ограничение 1"
  ],
  "used_issue_ids": [
    "ID-1",
    "ID-2"
  ]
}

Требования:
- short_answer: одна строка, без лишней воды
- evidence: 3-8 конкретных фактов по данным
- limitations: только реальные ограничения или осторожности
- used_issue_ids: только реальные ID из переданного контекста

Запрещено:
- придумывать несуществующие связи
- делать причинно-следственные выводы без опоры на поля задач
- подменять факты красивой формулировкой
"""


def _mode_instruction(mode: str) -> str:
    if mode == "similar":
        return (
            "Объясни, чем найденные задачи похожи на запрос. "
            "Выдели сильные и слабые совпадения. "
            "Не называй задачи полными аналогами, если совпадения только частичные."
        )

    if mode == "analyze_new_task":
        return (
            "Сравни новую формулировку пользователя с найденными задачами. "
            "Покажи сильные аналоги, слабые аналоги и пробелы в данных."
        )

    if mode == "general_search":
        return (
            "Сделай краткий управленческий вывод по найденным задачам. "
            "Если запрос широкий, сузь ответ до реально подтвержденных фактов."
        )

    if mode == "approval_status":
        return (
            "Сфокусируйся на согласованиях, стадиях, принятых или непринятых решениях "
            "и на том, где есть зависание процесса."
        )

    if mode == "overdue":
        return (
            "Сфокусируйся на просрочках, дедлайнах и том, что требует внимания. "
            "Не называй задачу критичной без фактов из данных."
        )

    if mode in {"stats", "count"}:
        return (
            "Сделай аналитический вывод по выборке и агрегатам, "
            "но не придумывай причины только на основе счетчиков."
        )

    if mode in {"list", "by_customer", "by_responsible", "with_remarks", "deadlines"}:
        return (
            "Сделай краткий операционный вывод по найденной выборке: "
            "что объединяет задачи, что выделяется, где нужен фокус."
        )

    return "Работай строго по найденным данным и не выходи за рамки контекста."


def _analysis_profile_instruction(analysis_profile: str) -> str:
    if analysis_profile == "deep":
        return (
            "Это режим глубокого анализа. "
            "Допустим более длинный и содержательный short_answer, "
            "но он все равно должен быть одной строкой. "
            "Сначала извлеки факты, потом сделай осторожный вывод."
        )

    return (
        "Это обычный аналитический режим. "
        "Ответ должен быть компактным, но полезным."
    )


def _mode_output_hint(mode: str) -> str:
    if mode == "similar":
        return (
            "short_answer: скажи, есть ли сильные аналоги.\n"
            "evidence: укажи совпадающие темы, статусы, типы документа, заказчиков, стадии.\n"
            "limitations: укажи, если аналогия неполная."
        )

    if mode == "analyze_new_task":
        return (
            "short_answer: оцени, есть ли хорошие аналоги новой задачи.\n"
            "evidence: перечисли сильные совпадения и различия.\n"
            "limitations: скажи, чего не хватает для полной уверенности."
        )

    if mode == "overdue":
        return (
            "short_answer: дай краткий вывод по просрочкам.\n"
            "evidence: укажи конкретные задачи, сроки и дни просрочки.\n"
            "limitations: укажи, если выборка неполная."
        )

    if mode in {"stats", "count"}:
        return (
            "short_answer: дай один вывод по структуре выборки.\n"
            "evidence: используй конкретные агрегаты и подтверждающие задачи.\n"
            "limitations: не переинтерпретируй счетчики."
        )

    return (
        "short_answer: один полезный вывод.\n"
        "evidence: только конкретные факты из задач.\n"
        "limitations: только реальные ограничения."
    )


def _format_deadlines(deadlines: dict) -> str:
    if not isinstance(deadlines, dict) or not deadlines:
        return ""

    parts = []
    for key, value in deadlines.items():
        value = safe_str(value)
        if value:
            parts.append(f"{key}={value}")

    return ", ".join(parts)


def _format_main_deadline(task: dict) -> str:
    main_deadline = task.get("main_deadline", {})
    if not isinstance(main_deadline, dict):
        return ""

    label = safe_str(main_deadline.get("label"))
    value = safe_str(main_deadline.get("value"))

    if not value:
        return ""

    return f"{label}: {value}" if label else value


def _format_pending_approvals(task: dict) -> str:
    pending = task.get("pending_approvals", [])
    if not isinstance(pending, list) or not pending:
        return ""

    return ", ".join(safe_str(x) for x in pending if safe_str(x))


def _format_approval_details(task: dict) -> str:
    items = task.get("approval_details", [])
    if not isinstance(items, list) or not items:
        return ""

    parts = []
    for item in items[:10]:
        if not isinstance(item, dict):
            continue

        label = safe_str(item.get("label"))
        value = safe_str(item.get("value"))
        if label and value:
            parts.append(f"{label}: {value}")

    return "; ".join(parts)


def _format_decisions(task: dict) -> str:
    mapping = [
        ("decision_dit", "ДИТ"),
        ("decision_gku", "ГКУ"),
        ("decision_dkp", "ДКП"),
        ("decision_dep", "ДЭПиР"),
    ]

    parts = []
    for field, label in mapping:
        value = safe_str(task.get(field))
        if value:
            parts.append(f"{label}: {value}")

    return "; ".join(parts)


def task_context(task: dict, analysis_profile: str = "fast") -> str:
    _, text_limit = _profile_limits(analysis_profile)

    fields = [
        ("ID", safe_str(task.get("issue_id"))),
        ("Заголовок", safe_str(task.get("summary"))),
        ("Статус", safe_str(task.get("status"))),
        ("Группа статуса", safe_str(task.get("workflow_group") or task.get("status_group"))),
        ("Приоритет", safe_str(task.get("priority"))),
        ("Тип документа", safe_str(task.get("doc_type"))),
        ("Функциональный заказчик", safe_str(task.get("functional_customer"))),
        ("Ответственный (ДИТ)", safe_str(task.get("responsible_dit"))),
        ("Инициатор согласования", safe_str(task.get("approval_initiator"))),
        ("Текущая стадия согласования", safe_str(task.get("current_approval_stage"))),
        ("Pending approvals", _format_pending_approvals(task)),
        ("Approval details", _format_approval_details(task)),
        ("Решения", _format_decisions(task)),
        ("Ближайший дедлайн", _format_main_deadline(task)),
        ("Все сроки", _format_deadlines(task.get("deadlines", {}))),
        ("Просрочено", "Да" if task.get("is_overdue") else ""),
        ("Дней просрочки", str(task.get("overdue_days")) if task.get("is_overdue") else ""),
        ("Описание", truncate(task.get("description", ""), text_limit)),
    ]

    lines = []
    for label, value in fields:
        if value:
            lines.append(f"{label}: {value}")

    return "\n".join(lines)


def _build_context_block(tasks: list[dict], analysis_profile: str) -> str:
    task_limit, _ = _profile_limits(analysis_profile)

    blocks = []
    for i, task in enumerate(tasks[:task_limit], start=1):
        blocks.append(f"--- Задача {i} ---\n{task_context(task, analysis_profile=analysis_profile)}")

    return "\n\n".join(blocks) if blocks else "Подходящие задачи не найдены."


def build_llm_prompt(
    user_query: str,
    tasks: list[dict],
    mode: str,
    analysis_profile: str = "fast",
    extra_context: str = "",
    memory_context: str = "",
) -> str:
    context = _build_context_block(tasks, analysis_profile)

    extra_context = safe_str(extra_context)
    if not extra_context:
        extra_context = "Дополнительной агрегированной аналитики нет."

    memory_context = safe_str(memory_context)
    if not memory_context:
        memory_context = "No prior live-chat memory digest."

    return f"""{SYSTEM_PROMPT}

Текущая дата и время (Europe/Stockholm):
{_now_label()}

Сегодняшняя дата:
{_today_label()}

Режим:
{mode}

Профиль анализа:
{analysis_profile}

Инструкция по режиму:
{_mode_instruction(mode)}

Инструкция по профилю:
{_analysis_profile_instruction(analysis_profile)}

Как формировать ответ:
{_mode_output_hint(mode)}

Запрос пользователя:
{user_query}

Memory context (continuity only, not factual evidence):
{memory_context}

Memory and grounding rules:
- Use memory only for conversational continuity (references, pronouns, follow-ups).
- Never use memory as factual evidence.
- Use only current retrieved tasks in this request as factual grounding.
- If current retrieval is weak or empty, do not invent facts and state limitations clearly.
Дополнительный агрегированный контекст:
{extra_context}

Найденные задачи:
{context}
"""


def build_critic_prompt(
    user_query: str,
    tasks: list[dict],
    mode: str,
    draft_result: dict,
    analysis_profile: str = "fast",
    extra_context: str = "",
    memory_context: str = "",
) -> str:
    """
    Второй проход:
    - проверяет groundedness
    - убирает неподтвержденные формулировки
    - сохраняет полезность ответа
    """
    context = _build_context_block(tasks, analysis_profile)
    extra_context = safe_str(extra_context)
    if not extra_context:
        extra_context = "Дополнительной агрегированной аналитики нет."

    memory_context = safe_str(memory_context)
    if not memory_context:
        memory_context = "No prior live-chat memory digest."

    draft_json = (
        str(draft_result)
        if not isinstance(draft_result, dict)
        else __import__("json").dumps(draft_result, ensure_ascii=False, indent=2)
    )

    return f"""{SYSTEM_PROMPT}

Ты выполняешь второй проход проверки ответа (critic pass).

Твоя задача:
1. Проверить, подтверждается ли черновой ответ контекстом.
2. Удалить любые неподтвержденные выводы.
3. Сохранить ответ полезным и аналитичным.
4. Если какой-то вывод слабый, перенести осторожность в limitations.
5. Сохранить только те used_issue_ids, которые реально подтверждаются контекстом.

Текущая дата и время (Europe/Moscow):
{_now_label()}

Сегодняшняя дата:
{_today_label()}

Режим:
{mode}

Профиль анализа:
{analysis_profile}

Исходный запрос пользователя:
{user_query}

Memory context (continuity only, not factual evidence):
{memory_context}

Memory and grounding rules:
- Use memory only for conversational continuity (references, pronouns, follow-ups).
- Never use memory as factual evidence.
- Use only current retrieved tasks in this request as factual grounding.
- If current retrieval is weak or empty, do not invent facts and state limitations clearly.
Дополнительный агрегированный контекст:
{extra_context}

Найденные задачи:
{context}

Черновой ответ analyst pass:
{draft_json}

Верни только исправленный JSON в том же формате.
"""
