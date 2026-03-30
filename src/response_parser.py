import json


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen = set()
    result = []

    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)

    return result


def _strip_code_fences(raw_text: str) -> str:
    text = raw_text.strip()

    if text.startswith("```"):
        lines = text.splitlines()

        if lines and lines[0].startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        text = "\n".join(lines).strip()

    return text


def _extract_first_json_object(raw_text: str) -> str:
    text = raw_text.strip()

    start = text.find("{")
    if start == -1:
        raise ValueError("В ответе модели не найден JSON-объект.")

    depth = 0
    in_string = False
    escape = False

    for idx in range(start, len(text)):
        ch = text[idx]

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch == "{":
            depth += 1
            continue

        if ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:idx + 1]

    raise ValueError("Не удалось выделить завершенный JSON-объект из ответа модели.")


def _normalize_string_list(value) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []

    if not isinstance(value, list):
        return []

    result = []
    for item in value:
        if item is None:
            continue

        if isinstance(item, str):
            text = item.strip()
            if text:
                result.append(text)
            continue

        if isinstance(item, (dict, list)):
            try:
                text = json.dumps(item, ensure_ascii=False)
            except Exception:
                text = str(item).strip()
        else:
            text = str(item).strip()

        if text:
            result.append(text)

    return _dedupe_keep_order(result)


def _normalize_short_answer(value) -> str:
    return str(value or "").strip()


def _normalize_result(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Ответ модели должен быть JSON-объектом.")

    return {
        "short_answer": _normalize_short_answer(data.get("short_answer", "")),
        "evidence": _normalize_string_list(data.get("evidence", [])),
        "limitations": _normalize_string_list(data.get("limitations", [])),
        "used_issue_ids": _normalize_string_list(data.get("used_issue_ids", [])),
    }


def parse_json_safely(raw_text: str) -> dict:
    raw_text = _strip_code_fences(raw_text).strip()

    if not raw_text:
        raise ValueError("Модель вернула пустой ответ.")

    try:
        return _normalize_result(json.loads(raw_text))
    except json.JSONDecodeError:
        fragment = _extract_first_json_object(raw_text)
        try:
            return _normalize_result(json.loads(fragment))
        except json.JSONDecodeError as e:
            raise ValueError(f"Не удалось распарсить JSON-ответ модели: {e}") from e


def validate_llm_result(parsed: dict, tasks: list[dict]) -> dict:
    if not isinstance(parsed, dict):
        raise ValueError("Ответ модели не является JSON-объектом.")

    allowed_ids = {
        str(t.get("issue_id")).strip()
        for t in tasks
        if t.get("issue_id")
    }

    short_answer = str(parsed.get("short_answer", "")).strip()
    if not short_answer:
        raise ValueError("В ответе модели нет short_answer.")

    used_ids = parsed.get("used_issue_ids", [])
    if not isinstance(used_ids, list):
        used_ids = []

    filtered_ids = []
    for item in used_ids:
        text = str(item).strip()
        if text and text in allowed_ids:
            filtered_ids.append(text)

    filtered_ids = _dedupe_keep_order(filtered_ids)

    evidence = _normalize_string_list(parsed.get("evidence", []))
    limitations = _normalize_string_list(parsed.get("limitations", []))

    if not evidence and tasks:
        fallback_evidence = []
        for task in tasks[:3]:
            issue_id = str(task.get("issue_id", "")).strip()
            status = str(task.get("status", "")).strip()
            summary = str(task.get("summary", "")).strip()

            parts = [p for p in [issue_id, status, summary] if p]
            if parts:
                fallback_evidence.append(" | ".join(parts))

        evidence = fallback_evidence
        limitations.append(
            "Модель не вернула evidence в нужном формате, поэтому добавлены минимальные факты из найденных задач."
        )

    if not filtered_ids and tasks:
        filtered_ids = [
            str(task.get("issue_id", "")).strip()
            for task in tasks
            if str(task.get("issue_id", "")).strip()
        ]

    filtered_ids = _dedupe_keep_order(filtered_ids)

    evidence = evidence[:8]
    limitations = _dedupe_keep_order(limitations)[:6]
    filtered_ids = filtered_ids[:12]

    if len(tasks) == 1:
        note = "Вывод основан на одной найденной задаче."
        if note not in limitations:
            limitations.append(note)

    return {
        "short_answer": short_answer,
        "evidence": evidence,
        "limitations": limitations,
        "used_issue_ids": filtered_ids,
    }