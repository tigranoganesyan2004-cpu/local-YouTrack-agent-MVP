import re

from src.utils import normalize_space, safe_str


FIELD_ALIASES = {
    "статус": "status",
    "status": "status",
    "raw_status": "raw_status",
    "сырой_статус": "raw_status",
    "группа": "workflow_group",
    "status_group": "status_group",
    "workflow_group": "workflow_group",
    "приоритет": "priority",
    "priority": "priority",
    "тип": "doc_type",
    "тип_документа": "doc_type",
    "документ": "doc_type",
    "doc_type": "doc_type",
    "заказчик": "functional_customer",
    "customer": "functional_customer",
    "functional_customer": "functional_customer",
    "ответственный": "responsible_dit",
    "responsible": "responsible_dit",
    "responsible_dit": "responsible_dit",
    "ид": "issue_id",
    "id": "issue_id",
    "issue_id": "issue_id",
}

COUNT_FIELD_ALIASES = {
    **FIELD_ALIASES,
    "статусам": "status",
    "приоритетам": "priority",
    "типам": "doc_type",
    "заказчикам": "functional_customer",
    "ответственным": "responsible_dit",
    "стадиям": "current_approval_stage",
    "согласующим": "current_approval_stage",
}

DEPARTMENT_ALIASES = {
    "dit": ["дит", "dit"],
    "gku": ["гку", "gku"],
    "dkp": ["дкп", "dkp"],
    "dep": ["дэпир", "депир", "дэпир", "depir"],
}

DEPARTMENT_META = {
    "dit": {
        "label": "ДИТ",
        "approval_field": "approval_dit",
        "decision_field": "decision_dit",
        "deadline_field": "deadline_dit",
    },
    "gku": {
        "label": "ГКУ",
        "approval_field": "approval_gku",
        "decision_field": "decision_gku",
        "deadline_field": "deadline_gku",
    },
    "dkp": {
        "label": "ДКП",
        "approval_field": "approval_dkp",
        "decision_field": "decision_dkp",
        "deadline_field": "deadline_dkp",
    },
    "dep": {
        "label": "ДЭПиР",
        "approval_field": "approval_dep",
        "decision_field": "decision_dep",
        "deadline_field": "deadline_dep",
    },
}


def extract_issue_id(text: str) -> str | None:
    text = safe_str(text)
    m = re.search(r"\b([A-Za-zА-Яа-яЁё0-9_]+-\d+)\b", text)
    return m.group(1) if m else None


def _strip_quotes(text: str) -> str:
    text = safe_str(text).strip()
    if len(text) >= 2 and text[0] in {"'", '"'} and text[-1] == text[0]:
        return text[1:-1].strip()
    return text


def parse_key_values(text_or_parts) -> dict:
    if isinstance(text_or_parts, list):
        text = " ".join(safe_str(x) for x in text_or_parts)
    else:
        text = safe_str(text_or_parts)

    pattern = re.compile(
        r'([A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*)\s*=\s*(".*?"|\'.*?\'|[^\s]+)'
    )

    filters = {}
    for key, value in pattern.findall(text):
        key = FIELD_ALIASES.get(key.strip().lower(), key.strip().lower())
        value = _strip_quotes(value)
        if value:
            filters[key] = value
    return filters


def _extract_days(text: str, default: int = 14) -> int:
    text = safe_str(text).lower()

    m = re.search(r"days\s*=\s*(\d+)", text)
    if m:
        return int(m.group(1))

    m = re.search(r"(\d+)\s*(дн|дня|дней)", text)
    if m:
        return int(m.group(1))

    m = re.search(r"(\d+)\s*(day|days)", text)
    if m:
        return int(m.group(1))

    return default


def _detect_priority(text: str) -> str | None:
    lower = text.lower()

    if "критич" in lower:
        return "Критический"
    if "высок" in lower:
        return "Высокий"
    if "средн" in lower:
        return "Средний"
    if "низк" in lower:
        return "Низкий"

    return None


def _detect_doc_type(text: str) -> str | None:
    lower = text.lower()

    if "постановк" in lower:
        return "Постановка"

    if "тз" in lower or "техническ" in lower:
        return "ТЗ"

    if "концепц" in lower:
        return "Концепция"

    return None


def _detect_department(text: str) -> str | None:
    lower = safe_str(text).lower()

    for code, variants in DEPARTMENT_ALIASES.items():
        for variant in variants:
            if re.search(rf"\b{re.escape(variant)}\b", lower):
                return code

    return None


def _department_meta(code: str | None) -> dict:
    if not code:
        return {}
    return DEPARTMENT_META.get(code, {})


def _detect_deadline_field(text: str) -> str | None:
    lower = safe_str(text).lower()

    if "устранения замечаний" in lower or "срок замечаний" in lower:
        return "deadline_fix_comments"

    if "первоначальный срок" in lower or "первоначального срока" in lower:
        return "initial_review_deadline"

    department = _detect_department(text)
    if department:
        if "срок согласования" in lower or "сроки согласования" in lower:
            return _department_meta(department).get("deadline_field")

    return None


def _detect_workflow_filter(text: str) -> tuple[dict, dict]:
    lower = safe_str(text).lower()
    filters = {}
    flags = {
        "active_only": None,
        "final_only": None,
        "overdue_only": False,
    }

    if "просроч" in lower or "горят" in lower or "нарушены сроки" in lower:
        flags["overdue_only"] = True
        if flags["active_only"] is None:
            flags["active_only"] = True

    if "активн" in lower or "в работе" in lower:
        flags["active_only"] = True
        flags["final_only"] = False

    if "завершенн" in lower or "закрыт" in lower or "финальн" in lower:
        flags["final_only"] = True
        flags["active_only"] = False

    if "на согласован" in lower or "на согл" in lower:
        filters["status"] = "Направлено на согл."
    elif "замечан" in lower and "устранения замечаний" not in lower:
        filters["workflow_group"] = "rework"
    elif "отказ" in lower or "отмен" in lower:
        filters["workflow_group"] = "rejected_or_cancelled"
    elif "не инициир" in lower:
        filters["workflow_group"] = "not_started"
    elif re.search(r"\bсогласовано\b", lower):
        filters["status"] = "Согласовано"

    return filters, flags


def _extract_explicit_filters_from_text(text: str) -> dict:
    raw_text = safe_str(text)
    lower = raw_text.lower()
    filters = {}

    priority = _detect_priority(raw_text)
    if priority:
        filters["priority"] = priority

    doc_type = _detect_doc_type(raw_text)
    if doc_type:
        filters["doc_type"] = doc_type

    customer_match = re.search(
        r"(?:заказчик(?:а|ом)?|customer)\s+([A-Za-zА-Яа-яЁё0-9_\-]{2,40})",
        raw_text,
        flags=re.IGNORECASE,
    )
    if customer_match:
        filters["functional_customer"] = customer_match.group(1)

    responsible_match = re.search(
        r"(?:ответствен(?:ный|ного)(?:\s*\(дит\))?|responsible)\s+([A-Za-zА-Яа-яЁё0-9_\-]{2,40})",
        raw_text,
        flags=re.IGNORECASE,
    )
    if responsible_match:
        filters["responsible_dit"] = responsible_match.group(1)

    if "responsible_dit" not in filters and "functional_customer" not in filters:
        m_latin = re.search(r"\bу\s+([A-Z][A-Z0-9_\-]{1,20})\b", raw_text)
        m_cyr = re.search(r"\bу\s+([А-ЯЁ]{2,20})\b", raw_text)

        if m_latin:
            filters["responsible_dit"] = m_latin.group(1)
        elif m_cyr:
            filters["functional_customer"] = m_cyr.group(1)

    status_match = re.search(
        r"(?:статус(?:у|ом|е)?|status)\s+(.+?)(?:$|,|;|\s+по\s+|\s+у\s+)",
        raw_text,
        flags=re.IGNORECASE,
    )
    if status_match and "status" not in filters:
        value = normalize_space(status_match.group(1))
        if value:
            filters["status"] = value

    return filters


def _detect_count_field(text: str) -> str:
    lower = safe_str(text).lower()

    m = re.search(r"(?:по|by)\s+([A-Za-zА-Яа-яЁё_]+)", lower)
    if m:
        return COUNT_FIELD_ALIASES.get(m.group(1), m.group(1))

    if "стад" in lower and "согласован" in lower:
        return "current_approval_stage"
    if "приоритет" in lower:
        return "priority"
    if "тип" in lower:
        return "doc_type"
    if "заказчик" in lower:
        return "functional_customer"
    if "ответствен" in lower:
        return "responsible_dit"
    if "статус" in lower:
        return "status"

    return "status"


def _detect_stats_field(text: str) -> str:
    lower = safe_str(text).lower()

    if "стад" in lower and "согласован" in lower:
        return "current_approval_stage"
    if "заказчик" in lower:
        return "functional_customer"
    if "ответствен" in lower or "кто вед" in lower:
        return "responsible_dit"
    if "приоритет" in lower:
        return "priority"
    if "тип" in lower:
        return "doc_type"
    if "workflow" in lower or "групп" in lower:
        return "workflow_group"

    return "status"


def _merge_filters(explicit_filters: dict, hint_filters: dict) -> dict:
    merged = dict(hint_filters)
    merged.update(explicit_filters)
    return merged


def _detect_approval_status_intent(text: str, filters: dict, flags: dict) -> dict | None:
    lower = safe_str(text).lower()
    department = _detect_department(text)

    approval_triggers = [
        "ждет согласования",
        "ждёт согласования",
        "статус согласования",
        "согласование с",
        "решение ",
    ]

    if not any(trigger in lower for trigger in approval_triggers):
        return None

    if not department:
        return None

    meta = _department_meta(department)
    if not meta:
        return None

    approval_bucket = None
    decision_missing = False

    if "решение " in lower and ("не принято" in lower or "еще не принято" in lower or "ещё не принято" in lower):
        decision_missing = True

    elif (
        "ждет согласования" in lower
        or "ждёт согласования" in lower
        or "не завершено" in lower
        or "не завершен" in lower
        or "не завершена" in lower
        or "ещё не завершено" in lower
        or "еще не завершено" in lower
        or "ожидает согласования" in lower
    ):
        approval_bucket = "pending"

    elif "согласовано с замеч" in lower:
        approval_bucket = "positive"
        filters["workflow_group"] = "approved_with_remarks"

    elif "отказ" in lower or "отмен" in lower:
        approval_bucket = "negative"

    return {
        "mode": "approval_status",
        "department": department,
        "department_label": meta["label"],
        "approval_field": meta["approval_field"],
        "decision_field": meta["decision_field"],
        "approval_bucket": approval_bucket,
        "decision_missing": decision_missing,
        "filters": filters,
        "active_only": True if flags["active_only"] is None else flags["active_only"],
        "final_only": flags["final_only"],
    }


def _detect_overdue_intent(text: str, filters: dict) -> dict | None:
    lower = safe_str(text).lower()

    overdue_markers = [
        "просроч",
        "горят",
        "нарушены сроки",
        "срок уже прош",
        "сроки истек",
        "сроки истёк",
    ]

    if not any(marker in lower for marker in overdue_markers):
        return None

    return {
        "mode": "overdue",
        "deadline_field": _detect_deadline_field(text),
        "filters": filters,
        "active_only": True,
    }


def _detect_with_remarks_intent(text: str, filters: dict, flags: dict) -> dict | None:
    lower = safe_str(text).lower()

    markers = [
        "с замечаниями",
        "выданы замечания",
        "получили замечания",
        "получил замечания",
    ]

    if not any(marker in lower for marker in markers):
        return None

    return {
        "mode": "with_remarks",
        "filters": filters,
        "active_only": flags["active_only"],
        "final_only": flags["final_only"],
    }


def _detect_stats_intent(text: str, filters: dict, flags: dict) -> dict | None:
    lower = safe_str(text).lower()

    if (
        "статистика" in lower
        or "распределение" in lower
        or "сводка" in lower
        or "dashboard" in lower
        or "сколько" in lower and "у каждого" in lower
    ):
        return {
            "mode": "stats",
            "field": _detect_stats_field(text),
            "filters": filters,
            "active_only": flags["active_only"],
            "final_only": flags["final_only"],
            "overdue_only": flags["overdue_only"],
        }

    return None


def _detect_by_customer_intent(text: str, filters: dict, flags: dict) -> dict | None:
    lower = safe_str(text).lower()

    if "заказчик" in lower:
        return {
            "mode": "by_customer",
            "filters": filters,
            "active_only": flags["active_only"],
            "final_only": flags["final_only"],
            "overdue_only": flags["overdue_only"],
        }

    if "functional_customer" in filters:
        return {
            "mode": "by_customer",
            "filters": filters,
            "active_only": flags["active_only"],
            "final_only": flags["final_only"],
            "overdue_only": flags["overdue_only"],
        }

    return None


def _detect_by_responsible_intent(text: str, filters: dict, flags: dict) -> dict | None:
    lower = safe_str(text).lower()

    if "ответствен" in lower or "кто вед" in lower:
        return {
            "mode": "by_responsible",
            "filters": filters,
            "active_only": flags["active_only"],
            "final_only": flags["final_only"],
            "overdue_only": flags["overdue_only"],
        }

    if "responsible_dit" in filters:
        return {
            "mode": "by_responsible",
            "filters": filters,
            "active_only": flags["active_only"],
            "final_only": flags["final_only"],
            "overdue_only": flags["overdue_only"],
        }

    return None


def detect_intent(user_query: str) -> dict:
    text = normalize_space(user_query)
    lower = text.lower()

    if not text:
        return {"mode": "help"}

    explicit_filters = parse_key_values(text)
    hint_filters, flags = _detect_workflow_filter(text)
    natural_filters = _extract_explicit_filters_from_text(text)
    filters = _merge_filters(explicit_filters, {**hint_filters, **natural_filters})

    issue_id = extract_issue_id(text)
    if issue_id:
        return {"mode": "task_by_id", "issue_id": issue_id}

    if lower in {"помощь", "help"}:
        return {"mode": "help"}

    parts = text.split()
    first_word = parts[0].lower() if parts else ""

    if first_word in {"ид", "id", "show", "показать"} and len(parts) >= 2:
        return {"mode": "task_by_id", "issue_id": parts[1]}

    if first_word in {"точно", "exact"}:
        query = text[len(parts[0]):].strip()
        return {"mode": "exact_search", "query": query}

    if first_word in {"похожие", "similar"}:
        query = text[len(parts[0]):].strip()
        return {"mode": "similar", "query": query}

    if first_word in {"анализ", "analyze", "проанализируй"}:
        query = text[len(parts[0]):].strip()
        return {"mode": "analyze_new_task", "query": query}

    if first_word in {"общий", "general", "llm", "rag"}:
        query = text[len(parts[0]):].strip()
        return {"mode": "general_search", "query": query}

    approval_intent = _detect_approval_status_intent(text, filters, flags)
    if approval_intent:
        return approval_intent

    overdue_intent = _detect_overdue_intent(text, filters)
    if overdue_intent:
        return overdue_intent

    remarks_intent = _detect_with_remarks_intent(text, filters, flags)
    if remarks_intent:
        return remarks_intent

    stats_intent = _detect_stats_intent(text, filters, flags)
    if stats_intent:
        return stats_intent

    by_customer_intent = _detect_by_customer_intent(text, filters, flags)
    if by_customer_intent:
        return by_customer_intent

    by_responsible_intent = _detect_by_responsible_intent(text, filters, flags)
    if by_responsible_intent:
        return by_responsible_intent

    if first_word in {"список", "list", "фильтр"}:
        return {
            "mode": "list",
            "filters": filters,
            "active_only": flags["active_only"],
            "final_only": flags["final_only"],
            "overdue_only": flags["overdue_only"],
        }

    if first_word in {"количество", "count", "посчитать"}:
        return {
            "mode": "count",
            "field": _detect_count_field(text),
            "filters": filters,
            "active_only": flags["active_only"],
            "final_only": flags["final_only"],
            "overdue_only": flags["overdue_only"],
        }

    if first_word in {"сроки", "дедлайны", "deadlines"}:
        return {
            "mode": "deadlines",
            "days": _extract_days(text, default=14),
            "overdue_only": flags["overdue_only"],
            "active_only": True if flags["active_only"] is None else flags["active_only"],
        }

    if "похож" in lower or "аналог" in lower:
        return {"mode": "similar", "query": text}

    if "новая задача" in lower or "новой постанов" in lower or "проанализируй" in lower:
        return {"mode": "analyze_new_task", "query": text}

    if "дедлайн" in lower or "срок" in lower:
        return {
            "mode": "deadlines",
            "days": _extract_days(text, default=14),
            "overdue_only": flags["overdue_only"],
            "active_only": True if flags["active_only"] is None else flags["active_only"],
        }

    if "сколько" in lower or "количество" in lower:
        return {
            "mode": "count",
            "field": _detect_count_field(text),
            "filters": filters,
            "active_only": flags["active_only"],
            "final_only": flags["final_only"],
            "overdue_only": flags["overdue_only"],
        }

    list_markers = [
        "какие задачи",
        "покажи задачи",
        "список задач",
        "найди задачи",
        "все задачи",
        "что сейчас",
        "что у ",
        "какие сейчас",
    ]
    if filters or any(marker in lower for marker in list_markers):
        return {
            "mode": "list",
            "filters": filters,
            "active_only": flags["active_only"],
            "final_only": flags["final_only"],
            "overdue_only": flags["overdue_only"],
        }

    return {"mode": "general_search", "query": text}