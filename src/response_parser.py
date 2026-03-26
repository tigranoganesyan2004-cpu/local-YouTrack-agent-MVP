import json


# response_parser.py отвечает за безопасный разбор JSON-ответа модели.
# Если модель вернула лишний текст, модуль пытается извлечь JSON-фрагмент.
# После этого результат дополнительно нормализуется под схему агента.


def _normalize_result(data: dict) -> dict:
    """
    Приводит ответ модели к стабильной схеме.

    Даже если модель слегка ошиблась по типам:
    - evidence вернула строкой,
    - limitations вернула строкой,
    - used_issue_ids вернула одной строкой,
    мы это исправим и не дадим агенту сломаться.
    """
    if not isinstance(data, dict):
        raise ValueError("Ответ модели должен быть JSON-объектом.")

    normalized = {
        "short_answer": data.get("short_answer", ""),
        "evidence": data.get("evidence", []),
        "limitations": data.get("limitations", []),
        "used_issue_ids": data.get("used_issue_ids", []),
    }

    # short_answer всегда должен быть строкой
    normalized["short_answer"] = str(normalized["short_answer"]).strip()

    # Приводим evidence к списку строк
    if isinstance(normalized["evidence"], str):
        normalized["evidence"] = [normalized["evidence"]]
    elif not isinstance(normalized["evidence"], list):
        normalized["evidence"] = []

    normalized["evidence"] = [str(x).strip() for x in normalized["evidence"] if str(x).strip()]

    # Приводим limitations к списку строк
    if isinstance(normalized["limitations"], str):
        normalized["limitations"] = [normalized["limitations"]]
    elif not isinstance(normalized["limitations"], list):
        normalized["limitations"] = []

    normalized["limitations"] = [str(x).strip() for x in normalized["limitations"] if str(x).strip()]

    # Приводим used_issue_ids к списку строк
    if isinstance(normalized["used_issue_ids"], str):
        normalized["used_issue_ids"] = [normalized["used_issue_ids"]]
    elif not isinstance(normalized["used_issue_ids"], list):
        normalized["used_issue_ids"] = []

    normalized["used_issue_ids"] = [str(x).strip() for x in normalized["used_issue_ids"] if str(x).strip()]

    return normalized


def parse_json_safely(raw_text: str) -> dict:
    """
    Пытается распарсить ответ модели как JSON.
    Сначала пробует весь текст целиком, затем fallback на JSON-фрагмент.
    """
    raw_text = raw_text.strip()

    if not raw_text:
        raise ValueError("Модель вернула пустой ответ.")

    try:
        return _normalize_result(json.loads(raw_text))
    except json.JSONDecodeError:
        start = raw_text.find("{")
        end = raw_text.rfind("}")

        if start != -1 and end != -1 and end > start:
            fragment = raw_text[start:end + 1]
            try:
                return _normalize_result(json.loads(fragment))
            except json.JSONDecodeError:
                pass

    raise ValueError("Не удалось распарсить JSON-ответ модели.")

def validate_llm_result(parsed: dict, tasks: list[dict]) -> dict:
    """
    Жесткая валидация уже распарсенного ответа модели.

    Здесь мы:
    - убеждаемся, что short_answer есть;
    - фильтруем used_issue_ids по реально найденным задачам;
    - приводим evidence/limitations к спискам.
    """
    allowed_ids = {t.get("issue_id") for t in tasks if t.get("issue_id")}

    if not isinstance(parsed, dict):
        raise ValueError("Ответ модели не является JSON-объектом.")

    if "short_answer" not in parsed or not str(parsed.get("short_answer", "")).strip():
        raise ValueError("В ответе модели нет short_answer.")

    used_ids = parsed.get("used_issue_ids", [])
    if not isinstance(used_ids, list):
        used_ids = []

    parsed["used_issue_ids"] = [x for x in used_ids if x in allowed_ids]

    if "evidence" not in parsed or not isinstance(parsed["evidence"], list):
        parsed["evidence"] = []

    if "limitations" not in parsed or not isinstance(parsed["limitations"], list):
        parsed["limitations"] = []

    return parsed