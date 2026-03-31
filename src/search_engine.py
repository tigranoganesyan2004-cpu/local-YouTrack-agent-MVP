from __future__ import annotations

from datetime import datetime, timedelta
import os

import numpy as np

from src.config import TASKS_JSON, USE_RERANKER
from src.utils import load_json, normalize_space, parse_iso_datetime, safe_str, tokenize
from src.vector_store import load_index
from src.ollama_client import ollama_client
from src.reranker import rerank
from src.query_parser import extract_issue_id, parse_key_values
from src.status_mapper import (
    is_final_status_group,
    normalize_approval_bucket,
    normalize_status,
)


_TASKS_CACHE: list[dict] | None = None
_TASKS_CACHE_MTIME: float | None = None


APPROVAL_BUCKET_MAP = {
    "pending": {"review", "rework", "not_started"},
    "positive": {"approved", "approved_with_remarks", "not_required"},
    "negative": {"rejected_or_cancelled"},
}

APPROVAL_FIELDS = [
    "approval_dit",
    "approval_gku",
    "approval_dkp",
    "approval_dep",
    "approval_price_refs",
    "approval_arm_expert",
    "approval_standardization",
]

DECISION_FIELDS = [
    "decision_dit",
    "decision_gku",
    "decision_dkp",
    "decision_dep",
]


def load_tasks() -> list[dict]:
    global _TASKS_CACHE, _TASKS_CACHE_MTIME

    if not TASKS_JSON.exists():
        return []

    mtime = os.path.getmtime(TASKS_JSON)

    if _TASKS_CACHE is None or _TASKS_CACHE_MTIME != mtime:
        _TASKS_CACHE = load_json(TASKS_JSON)
        _TASKS_CACHE_MTIME = mtime

    return _TASKS_CACHE or []


def clear_tasks_cache() -> None:
    global _TASKS_CACHE, _TASKS_CACHE_MTIME
    _TASKS_CACHE = None
    _TASKS_CACHE_MTIME = None


def _normalize_text(value: str) -> str:
    return normalize_space(safe_str(value)).lower()


def _parse_dt(value: str) -> datetime | None:
    return parse_iso_datetime(value)


def _dt_sort_key(value: str) -> float:
    dt = _parse_dt(value)
    return dt.timestamp() if dt else 0.0


def _text_equals(left: str, right: str) -> bool:
    return _normalize_text(left) == _normalize_text(right)


def _text_contains(left: str, right: str) -> bool:
    left_norm = _normalize_text(left)
    right_norm = _normalize_text(right)

    if not left_norm or not right_norm:
        return False

    return right_norm in left_norm or left_norm in right_norm


def _match_field(task_value: str, expected_value: str) -> bool:
    if not safe_str(expected_value):
        return True

    return _text_equals(task_value, expected_value) or _text_contains(task_value, expected_value)


def find_task_by_id(issue_id: str) -> dict | None:
    issue_id = safe_str(issue_id).upper()

    for task in load_tasks():
        task_issue_id = safe_str(task.get("issue_id")).upper()
        if task_issue_id == issue_id:
            return task

    return None


def is_final_task(task: dict) -> bool:
    if "is_final" in task:
        return bool(task.get("is_final"))

    if safe_str(task.get("resolved_at")):
        return True

    workflow_group = safe_str(task.get("workflow_group"))
    if workflow_group and is_final_status_group(workflow_group):
        return True

    raw_status = safe_str(task.get("raw_status"))
    if raw_status in {"Согласовано", "Согласовано с замеч.", "Отказано", "Согл. отменено"}:
        return True

    return False


def is_active_task(task: dict) -> bool:
    if "is_active" in task:
        return bool(task.get("is_active"))
    return not is_final_task(task)


def task_has_remarks(task: dict) -> bool:
    status = _normalize_text(task.get("status"))
    raw_status = _normalize_text(task.get("raw_status"))

    if "замеч" in status or "замеч" in raw_status:
        return True

    for field in APPROVAL_FIELDS + DECISION_FIELDS:
        value = _normalize_text(task.get(field))
        if "замеч" in value:
            return True

    return False


def get_task_deadlines(task: dict) -> list[dict]:
    if isinstance(task.get("deadline_entries"), list) and task.get("deadline_entries"):
        items = []
        for item in task["deadline_entries"]:
            dt = _parse_dt(item.get("value"))
            if dt is None:
                continue
            items.append(
                {
                    "field": safe_str(item.get("field")),
                    "label": safe_str(item.get("label")),
                    "value": safe_str(item.get("value")),
                    "dt": dt,
                }
            )
        items.sort(key=lambda x: x["dt"])
        return items

    return []


def get_main_deadline(task: dict) -> dict | None:
    main = task.get("main_deadline")
    if isinstance(main, dict) and safe_str(main.get("value")):
        dt = _parse_dt(main.get("value"))
        if dt is not None:
            return {
                "field": safe_str(main.get("field")),
                "label": safe_str(main.get("label")),
                "value": safe_str(main.get("value")),
                "dt": dt,
            }

    deadlines = get_task_deadlines(task)
    return deadlines[0] if deadlines else None


def task_has_overdue_deadline(task: dict, deadline_field: str | None = None, now: datetime | None = None) -> bool:
    now = now or datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    if deadline_field:
        raw = safe_str(task.get(deadline_field))
        dt = _parse_dt(raw)
        return bool(dt and dt.date() < now.date() and is_active_task(task))

    if "is_overdue" in task:
        return bool(task.get("is_overdue"))

    for item in get_task_deadlines(task):
        if item["dt"].date() < now.date() and is_active_task(task):
            return True

    return False


def _task_matches_approval_bucket(task: dict, approval_field: str, bucket: str | None) -> bool:
    value = safe_str(task.get(approval_field))
    if not value:
        return False

    if not bucket:
        return True

    approval_bucket = normalize_approval_bucket(value)
    allowed = APPROVAL_BUCKET_MAP.get(bucket)
    if not allowed:
        return approval_bucket == bucket

    return approval_bucket in allowed


def _task_matches_base_filters(
    task: dict,
    status: str | None = None,
    raw_status: str | None = None,
    status_group: str | None = None,
    workflow_group: str | None = None,
    priority: str | None = None,
    doc_type: str | None = None,
    functional_customer: str | None = None,
    responsible_dit: str | None = None,
    current_approval_stage: str | None = None,
    active_only: bool | None = None,
    final_only: bool | None = None,
    overdue_only: bool = False,
    deadline_field: str | None = None,
    with_remarks: bool = False,
) -> bool:
    if status and not _match_field(task.get("status", ""), status):
        return False

    if raw_status and not _match_field(task.get("raw_status", ""), raw_status):
        return False

    if status_group and not _match_field(task.get("status_group", ""), status_group):
        return False

    if workflow_group and not _match_field(task.get("workflow_group", ""), workflow_group):
        return False

    if priority and not _match_field(task.get("priority", ""), priority):
        return False

    if doc_type and not _match_field(task.get("doc_type", ""), doc_type):
        return False

    if functional_customer and not _match_field(task.get("functional_customer", ""), functional_customer):
        return False

    if responsible_dit and not _match_field(task.get("responsible_dit", ""), responsible_dit):
        return False

    if current_approval_stage and not _match_field(task.get("current_approval_stage", ""), current_approval_stage):
        return False

    if active_only is True and not is_active_task(task):
        return False

    if final_only is True and not is_final_task(task):
        return False

    if overdue_only and not task_has_overdue_deadline(task, deadline_field=deadline_field):
        return False

    if with_remarks and not task_has_remarks(task):
        return False

    return True


def _sort_tasks(tasks: list[dict], by_deadline_first: bool = False) -> list[dict]:
    if by_deadline_first:
        def key(task: dict):
            main_deadline = get_main_deadline(task)
            updated_key = _dt_sort_key(task.get("updated_at"))
            overdue_days = int(task.get("overdue_days") or 0)
            deadline_dt = main_deadline["dt"] if main_deadline else datetime.max
            return (-overdue_days, deadline_dt, -updated_key)

        return sorted(tasks, key=key)

    return sorted(tasks, key=lambda t: _dt_sort_key(t.get("updated_at")), reverse=True)


def filter_tasks(
    status: str | None = None,
    raw_status: str | None = None,
    status_group: str | None = None,
    workflow_group: str | None = None,
    priority: str | None = None,
    doc_type: str | None = None,
    functional_customer: str | None = None,
    responsible_dit: str | None = None,
    current_approval_stage: str | None = None,
    active_only: bool | None = None,
    final_only: bool | None = None,
    overdue_only: bool = False,
    deadline_field: str | None = None,
    with_remarks: bool = False,
    approval_field: str | None = None,
    approval_bucket: str | None = None,
    decision_field: str | None = None,
    decision_missing: bool = False,
    limit: int | None = None,
) -> list[dict]:
    results = []

    for task in load_tasks():
        if not _task_matches_base_filters(
            task,
            status=status,
            raw_status=raw_status,
            status_group=status_group,
            workflow_group=workflow_group,
            priority=priority,
            doc_type=doc_type,
            functional_customer=functional_customer,
            responsible_dit=responsible_dit,
            current_approval_stage=current_approval_stage,
            active_only=active_only,
            final_only=final_only,
            overdue_only=overdue_only,
            deadline_field=deadline_field,
            with_remarks=with_remarks,
        ):
            continue

        if approval_field and not _task_matches_approval_bucket(task, approval_field, approval_bucket):
            continue

        if decision_field and decision_missing and safe_str(task.get(decision_field)):
            continue

        results.append(task)

    results = _sort_tasks(results, by_deadline_first=overdue_only)

    if limit is not None:
        return results[:limit]

    return results


def find_tasks_by_approval(
    approval_field: str,
    approval_bucket: str | None = None,
    decision_field: str | None = None,
    decision_missing: bool = False,
    status: str | None = None,
    raw_status: str | None = None,
    status_group: str | None = None,
    workflow_group: str | None = None,
    priority: str | None = None,
    doc_type: str | None = None,
    functional_customer: str | None = None,
    responsible_dit: str | None = None,
    active_only: bool | None = True,
    final_only: bool | None = None,
    limit: int | None = None,
) -> list[dict]:
    return filter_tasks(
        status=status,
        raw_status=raw_status,
        status_group=status_group,
        workflow_group=workflow_group,
        priority=priority,
        doc_type=doc_type,
        functional_customer=functional_customer,
        responsible_dit=responsible_dit,
        active_only=active_only,
        final_only=final_only,
        approval_field=approval_field,
        approval_bucket=approval_bucket,
        decision_field=decision_field,
        decision_missing=decision_missing,
        limit=limit,
    )


def find_tasks_with_remarks(
    status: str | None = None,
    raw_status: str | None = None,
    status_group: str | None = None,
    workflow_group: str | None = None,
    priority: str | None = None,
    doc_type: str | None = None,
    functional_customer: str | None = None,
    responsible_dit: str | None = None,
    active_only: bool | None = None,
    final_only: bool | None = None,
    limit: int | None = None,
) -> list[dict]:
    return filter_tasks(
        status=status,
        raw_status=raw_status,
        status_group=status_group,
        workflow_group=workflow_group,
        priority=priority,
        doc_type=doc_type,
        functional_customer=functional_customer,
        responsible_dit=responsible_dit,
        active_only=active_only,
        final_only=final_only,
        with_remarks=True,
        limit=limit,
    )


def _build_overdue_entry(task: dict, item: dict, now: datetime) -> dict:
    overdue_days = (now.date() - item["dt"].date()).days

    return {
        "issue_id": task.get("issue_id", ""),
        "summary": task.get("summary", ""),
        "status": task.get("status", ""),
        "priority": task.get("priority", ""),
        "functional_customer": task.get("functional_customer", ""),
        "responsible_dit": task.get("responsible_dit", ""),
        "current_approval_stage": task.get("current_approval_stage", ""),
        "deadline_field": item["field"],
        "deadline_label": item["label"],
        "deadline_value": item["value"],
        "overdue_days": overdue_days,
    }


def find_overdue_entries(
    deadline_field: str | None = None,
    status: str | None = None,
    raw_status: str | None = None,
    status_group: str | None = None,
    workflow_group: str | None = None,
    priority: str | None = None,
    doc_type: str | None = None,
    functional_customer: str | None = None,
    responsible_dit: str | None = None,
    active_only: bool | None = True,
    final_only: bool | None = None,
    limit: int | None = None,
) -> list[dict]:
    now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    entries = []

    tasks = filter_tasks(
        status=status,
        raw_status=raw_status,
        status_group=status_group,
        workflow_group=workflow_group,
        priority=priority,
        doc_type=doc_type,
        functional_customer=functional_customer,
        responsible_dit=responsible_dit,
        active_only=active_only,
        final_only=final_only,
        overdue_only=True,
        deadline_field=deadline_field,
    )

    for task in tasks:
        if deadline_field:
            value = safe_str(task.get(deadline_field))
            dt = _parse_dt(value)
            if dt and dt.date() < now.date():
                entries.append(
                    _build_overdue_entry(
                        task,
                        {
                            "field": deadline_field,
                            "label": task.get("main_deadline", {}).get("label") if deadline_field == safe_str(task.get("main_deadline", {}).get("field")) else deadline_field,
                            "value": value,
                            "dt": dt,
                        },
                        now,
                    )
                )
            continue

        overdue_items = [item for item in get_task_deadlines(task) if item["dt"].date() < now.date()]
        if not overdue_items:
            continue

        earliest_overdue = sorted(overdue_items, key=lambda x: x["dt"])[0]
        entries.append(_build_overdue_entry(task, earliest_overdue, now))

    entries.sort(key=lambda x: (-int(x.get("overdue_days") or 0), x.get("deadline_value", "")))

    if limit is not None:
        return entries[:limit]

    return entries


def dataset_kpis(tasks: list[dict] | None = None) -> dict:
    tasks = tasks if tasks is not None else load_tasks()

    total = len(tasks)
    active = sum(1 for t in tasks if is_active_task(t))
    final = sum(1 for t in tasks if is_final_task(t))
    overdue = sum(1 for t in tasks if task_has_overdue_deadline(t))
    with_remarks = sum(1 for t in tasks if task_has_remarks(t))
    pending_approvals = sum(1 for t in tasks if t.get("pending_approvals"))

    return {
        "total": total,
        "active": active,
        "final": final,
        "overdue": overdue,
        "with_remarks": with_remarks,
        "pending_approvals": pending_approvals,
    }


def aggregate_counts(field: str, tasks: list[dict]) -> list[tuple[str, int]]:
    counter = {}

    for task in tasks:
        value = task.get(field)

        if isinstance(value, list):
            if not value:
                value = "<пусто>"
                counter[value] = counter.get(value, 0) + 1
            else:
                for item in value:
                    key = safe_str(item) or "<пусто>"
                    counter[key] = counter.get(key, 0) + 1
            continue

        key = safe_str(value) or "<пусто>"
        counter[key] = counter.get(key, 0) + 1

    return sorted(counter.items(), key=lambda x: (x[1], x[0]), reverse=True)


def lexical_score(query_tokens: list[str], task: dict) -> float:
    if not query_tokens:
        return 0.0

    fields = [
        ("issue_id", 6.0),
        ("summary", 5.0),
        ("semantic_text", 4.0),
        ("metadata_text", 1.5),
    ]

    score = 0.0
    query_set = set(query_tokens)

    for field, weight in fields:
        tokens = set(tokenize(task.get(field, "")))
        if not tokens:
            continue

        overlap = len(query_set & tokens)
        if overlap:
            score += weight * (overlap / max(len(query_set), 1))

    return score


def lexical_search(query: str, top_k: int = 5, status_group: str | None = None) -> list[dict]:
    query_tokens = tokenize(query)
    scored = []

    for task in load_tasks():
        if status_group and not _match_field(task.get("status_group", ""), status_group):
            continue

        score = lexical_score(query_tokens, task)
        if score > 0:
            scored.append((score, _dt_sort_key(task.get("updated_at")), task))

    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [task for _, _, task in scored[:top_k]]


def exact_search(query: str, top_k: int = 10) -> list[dict]:
    query = safe_str(query)
    if not query:
        return []

    issue_id = extract_issue_id(query)
    if issue_id:
        task = find_task_by_id(issue_id)
        return [task] if task else []

    kv_filters = parse_key_values(query)
    if kv_filters:
        return filter_tasks(
            status=kv_filters.get("status"),
            raw_status=kv_filters.get("raw_status"),
            status_group=kv_filters.get("status_group"),
            workflow_group=kv_filters.get("workflow_group"),
            priority=kv_filters.get("priority"),
            doc_type=kv_filters.get("doc_type"),
            functional_customer=kv_filters.get("functional_customer"),
            responsible_dit=kv_filters.get("responsible_dit"),
            limit=top_k,
        )

    query_tokens = tokenize(query)
    query_norm = _normalize_text(query)
    scored = []

    for task in load_tasks():
        score = 0.0

        exact_fields = [
            ("issue_id", 100.0),
            ("status", 80.0),
            ("raw_status", 75.0),
            ("priority", 70.0),
            ("doc_type", 70.0),
            ("functional_customer", 65.0),
            ("responsible_dit", 65.0),
            ("workflow_group", 60.0),
            ("current_approval_stage", 55.0),
        ]

        contains_fields = [
            ("summary", 40.0),
            ("semantic_text", 25.0),
            ("metadata_text", 15.0),
        ]

        for field, weight in exact_fields:
            value = safe_str(task.get(field))
            if not value:
                continue

            if _text_equals(value, query_norm):
                score += weight
            elif _text_contains(value, query_norm):
                score += weight * 0.55

        for field, weight in contains_fields:
            value = safe_str(task.get(field))
            if not value:
                continue

            if _text_contains(value, query_norm):
                score += weight

        score += lexical_score(query_tokens, task)

        if score > 0:
            scored.append((score, _dt_sort_key(task.get("updated_at")), task))

    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [task for _, _, task in scored[:top_k]]


def semantic_search(query: str, top_k: int = 5, status_group: str | None = None) -> list[dict]:
    index, mapping = load_index()
    if index is None:
        return []

    tasks = load_tasks()
    tasks_by_id = {t["issue_id"]: t for t in tasks if t.get("issue_id")}

    try:
        query_vector = np.array([ollama_client.embed(query)], dtype="float32")
        distances, indices = index.search(query_vector, top_k * 4)
    except Exception:
        return []

    issue_ids = []
    seen = set()

    for idx in indices[0]:
        if idx == -1:
            continue

        if idx >= len(mapping):
            continue

        issue_id = mapping[idx].get("issue_id", "")
        if not issue_id or issue_id in seen:
            continue

        task = tasks_by_id.get(issue_id)
        if task is None:
            continue

        if status_group and not _match_field(task.get("status_group", ""), status_group):
            continue

        seen.add(issue_id)
        issue_ids.append(issue_id)

        if len(issue_ids) >= top_k:
            break

    return [tasks_by_id[iid] for iid in issue_ids if iid in tasks_by_id]


def rrf_fuse(rankings: list[list[str]], k: int = 60) -> list[str]:
    scores = {}

    for ranking in rankings:
        for rank, issue_id in enumerate(ranking, start=1):
            scores[issue_id] = scores.get(issue_id, 0.0) + 1.0 / (k + rank)

    return [issue_id for issue_id, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)]


def hybrid_search(query: str, top_k: int = 5, status_group: str | None = None) -> list[dict]:
    tasks = load_tasks()
    tasks_by_id = {t["issue_id"]: t for t in tasks if t.get("issue_id")}

    exact_ids = [t["issue_id"] for t in exact_search(query, top_k=top_k * 2)]
    lexical_ids = [t["issue_id"] for t in lexical_search(query, top_k=top_k * 3, status_group=status_group)]
    semantic_ids = [t["issue_id"] for t in semantic_search(query, top_k=top_k * 3, status_group=status_group)]

    fused_ids = rrf_fuse([exact_ids, lexical_ids, semantic_ids])
    if not fused_ids:
        return []

    candidate_limit = top_k * 3 if USE_RERANKER else top_k

    seen = set()
    candidates = []

    for issue_id in fused_ids:
        if issue_id in seen:
            continue

        seen.add(issue_id)
        task = tasks_by_id.get(issue_id)
        if task:
            candidates.append(task)

        if len(candidates) >= candidate_limit:
            break

    if USE_RERANKER and len(candidates) > 1:
        candidates = rerank(query, candidates, top_k=top_k)
    else:
        candidates = candidates[:top_k]

    return candidates


def find_related_tasks(base_task: dict, limit: int = 5) -> list[dict]:
    scored = []
    base_tokens = tokenize(
        safe_str(base_task.get("summary")) + " " + safe_str(base_task.get("semantic_text"))
    )

    for task in load_tasks():
        if task.get("issue_id") == base_task.get("issue_id"):
            continue

        score = 0.0

        if safe_str(task.get("functional_customer")) == safe_str(base_task.get("functional_customer")):
            score += 2.0

        if safe_str(task.get("doc_type")) == safe_str(base_task.get("doc_type")):
            score += 1.5

        if safe_str(task.get("responsible_dit")) == safe_str(base_task.get("responsible_dit")):
            score += 1.0

        if safe_str(task.get("workflow_group")) == safe_str(base_task.get("workflow_group")):
            score += 0.8

        score += lexical_score(base_tokens, task)

        if score > 0:
            scored.append((score, _dt_sort_key(task.get("updated_at")), task))

    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [task for _, _, task in scored[:limit]]


def upcoming_deadlines(days: int = 14, overdue_only: bool = False, active_only: bool = True) -> list[dict]:
    now = datetime.now()
    threshold = now + timedelta(days=days)
    results = []

    for task in load_tasks():
        if active_only and not is_active_task(task):
            continue

        for item in get_task_deadlines(task):
            dt = item["dt"]

            if overdue_only:
                if dt >= now:
                    continue
            else:
                if not (now <= dt <= threshold):
                    continue

            delta_days = (dt.date() - now.date()).days

            results.append(
                {
                    "issue_id": task.get("issue_id", ""),
                    "summary": task.get("summary", ""),
                    "status": task.get("status", ""),
                    "deadline_field": item["field"],
                    "deadline_label": item["label"],
                    "deadline_value": item["value"],
                    "responsible_dit": task.get("responsible_dit", ""),
                    "functional_customer": task.get("functional_customer", ""),
                    "days_to_deadline": delta_days if delta_days >= 0 else None,
                    "overdue_days": abs(delta_days) if delta_days < 0 else 0,
                }
            )

    results.sort(key=lambda x: x["deadline_value"])
    return results