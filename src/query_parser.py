import re


FIELD_ALIASES = {
    "status": "status",
    "raw_status": "raw_status",
    "status_group": "status_group",
    "workflow_group": "workflow_group",
    "group": "workflow_group",
    "priority": "priority",
    "doc_type": "doc_type",
    "doctype": "doc_type",
    "customer": "functional_customer",
    "functional_customer": "functional_customer",
    "responsible": "responsible_dit",
    "responsible_dit": "responsible_dit",
}

def extract_issue_id(text: str) -> str | None:
    m = re.search(r"([A-Za-zА-Яа-я0-9_]+-\d+)", text)
    return m.group(1) if m else None


def parse_key_values(parts: list[str]) -> dict:
    filters = {}
    for part in parts:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip().lower()
        value = value.strip()
        if not value:
            continue
        key = FIELD_ALIASES.get(key, key)
        filters[key] = value
    return filters


def detect_intent(user_query: str) -> dict:
    text = user_query.strip()
    lower = text.lower()
    parts = text.split()

    if lower == "help":
        return {"mode": "help"}

    # команды по первому слову
    first_word = parts[0].lower() if parts else ""

    if first_word == "exact":
        return {"mode": "exact_search", "query": text[len(parts[0]):].strip()}

    if first_word == "rag":
        return {"mode": "general_search", "query": text[len(parts[0]):].strip()}
    
    if first_word in {"id", "show", "ид", "покажи"} and len(parts) >= 2:
        return {"mode": "task_by_id", "issue_id": parts[1]}

    if first_word in {"similar", "похожие", "похож"}:
        return {"mode": "similar", "query": text[len(parts[0]):].strip()}

    if first_word in {"analyze", "анализ", "проанализируй"}:
        return {"mode": "analyze_new_task", "query": text[len(parts[0]):].strip()}

    if first_word in {"general", "общий", "общее"}:
        return {"mode": "general_search", "query": text[len(parts[0]):].strip()}

    if first_word in {"list", "список", "фильтр"}:
        return {"mode": "list", "filters": parse_key_values(parts[1:])}

    if first_word in {"count", "количество", "посчитать"}:
        field = "status"
        lowered_parts = [p.lower() for p in parts]

        if "by" in lowered_parts:
            idx = lowered_parts.index("by")
            if idx + 1 < len(parts):
                field = FIELD_ALIASES.get(parts[idx + 1].lower(), parts[idx + 1])

        elif "по" in lowered_parts:
            idx = lowered_parts.index("по")
            if idx + 1 < len(parts):
                field = FIELD_ALIASES.get(parts[idx + 1].lower(), parts[idx + 1])

        filters = parse_key_values(parts[1:])
        return {"mode": "count", "field": field, "filters": filters}

    if first_word in {"deadlines", "сроки", "дедлайны"}:
        days = 14
        for part in parts[1:]:
            if part.startswith("days="):
                try:
                    days = int(part.split("=", 1)[1])
                except ValueError:
                    pass
        return {"mode": "deadlines", "days": days}
    issue_id = extract_issue_id(text)
    if issue_id:
        return {"mode": "task_by_id", "issue_id": issue_id}

    if "похож" in lower or "аналог" in lower:
        return {"mode": "similar", "query": text}

    if "новая задача" in lower or "новой постанов" in lower or "проанализируй" in lower:
        return {"mode": "analyze_new_task", "query": text}

    if "дедлайн" in lower or "срок" in lower:
        days = 14
        m = re.search(r"(\d+)\s*дн", lower)
        if m:
            days = int(m.group(1))
        return {"mode": "deadlines", "days": days}

    return {"mode": "general_search", "query": text}
