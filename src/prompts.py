from src.config import MAX_TEXT_CHARS, MAX_CONTEXT_TASKS
from src.utils import truncate, safe_str


# prompts.py отвечает за построение prompt'ов для LLM:
# системной инструкции, контекста задач и итогового запроса к модели.


SYSTEM_PROMPT = """Ты — локальный аналитический агент по задачам YouTrack.

Работай строго по правилам:

1. Используй только переданные задачи и только их поля.
2. Не придумывай связи, причины, статусы, сроки, решения и выводы, которых нет в данных.
3. Если данных недостаточно, обязательно укажи это в limitations.
4. Если задачи не найдены, честно скажи, что релевантные задачи не найдены.
5. used_issue_ids можно брать только из реально переданных задач.
6. Не добавляй ID, которых нет в контексте.
7. Не пиши ничего вне JSON.
8. Верни только один JSON-объект.

JSON-формат ответа:
{
  "short_answer": "краткий вывод",
  "evidence": ["факт 1", "факт 2"],
  "limitations": ["ограничение 1"],
  "used_issue_ids": ["ID-1", "ID-2"]
}

Требования к полям:
- short_answer: строка
- evidence: массив строк
- limitations: массив строк
- used_issue_ids: массив строк

Если уверенного ответа нет:
- short_answer должен быть осторожным;
- limitations должны прямо говорить, чего не хватает.
"""


def _mode_instruction(mode: str) -> str:
    """
    Отдельная инструкция по режиму.

    Это важно, потому что 'similar', 'analyze_new_task' и 'general_search'
    используют один и тот же LLM, но должны отвечать по-разному.
    """
    if mode == "similar":
        return (
            "Объясни, чем найденные задачи похожи на запрос пользователя. "
            "Не утверждай сходство, если оно не подтверждается полями задач."
        )

    if mode == "analyze_new_task":
        return (
            "Сравни новую постановку с найденными аналогами. "
            "Укажи, какие признаки похожи, а какие не подтверждены данными."
        )

    if mode == "general_search":
        return (
            "Сделай краткий аналитический вывод по найденным задачам. "
            "Не выходи за рамки переданного контекста."
        )

    return "Работай строго по найденным данным."


def _format_deadlines(deadlines: dict) -> str:
    """
    Превращает словарь дедлайнов в человекочитаемую строку.
    Это чище для prompt'а, чем сырой dict Python.
    """
    if not deadlines:
        return ""

    parts = []
    for key, value in deadlines.items():
        value = safe_str(value)
        if value:
            parts.append(f"{key}={value}")

    return ", ".join(parts)


def task_context(task: dict) -> str:
    """
    Превращает одну задачу в компактный, но информативный блок контекста.
    Показываем только полезные поля и не печатаем пустые.
    """
    fields = [
        ("ID", safe_str(task.get("issue_id"))),
        ("Заголовок", safe_str(task.get("summary"))),
        ("Статус", safe_str(task.get("status"))),
        ("Группа статуса", safe_str(task.get("workflow_group") or task.get("status_group"))),
        ("Приоритет", safe_str(task.get("priority"))),
        ("Тип документа", safe_str(task.get("doc_type"))),
        ("Функциональный заказчик", safe_str(task.get("functional_customer"))),
        ("Ответственный (ДИТ)", safe_str(task.get("responsible_dit"))),
        ("Инициатор", safe_str(task.get("approval_initiator"))),
        ("Сроки", _format_deadlines(task.get("deadlines", {}))),
        ("Описание", truncate(task.get("description", ""), MAX_TEXT_CHARS)),
    ]

    lines = []
    for label, value in fields:
        if value:
            lines.append(f"{label}: {value}")

    return "\n".join(lines)


def build_llm_prompt(user_query: str, tasks: list[dict], mode: str) -> str:
    """
    Собирает финальный prompt для модели:
    - SYSTEM_PROMPT
    - инструкция по режиму
    - запрос пользователя
    - найденный контекст
    """
    context_blocks = []
    for i, task in enumerate(tasks[:MAX_CONTEXT_TASKS], start=1):
        context_blocks.append(f"--- Задача {i} ---\n{task_context(task)}")

    context = "\n\n".join(context_blocks) if context_blocks else "Подходящие задачи не найдены."

    return f"""{SYSTEM_PROMPT}

Режим:
{mode}

Инструкция по режиму:
{_mode_instruction(mode)}

Запрос пользователя:
{user_query}

Найденные данные:
{context}
"""