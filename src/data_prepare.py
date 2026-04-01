from collections import Counter
from datetime import datetime

from src.config import DATASET_REPORT_JSON, TASKS_JSON
from src.data_loader import load_source_dataframe
from src.dataset_lifecycle import (
    prepare_dataset_replacement_if_needed,
    register_prepared_dataset,
)
from src.schema import (
    APPROVAL_LABELS,
    APPROVAL_TARGET_FIELDS,
    COLUMN_MAP,
    DATE_TARGET_FIELDS,
    DEADLINE_LABELS,
    DEADLINE_TARGET_FIELDS,
    DEDUP_SCORE_FIELDS,
    EMPTY_PLACEHOLDERS_BY_TARGET,
    REQUIRED_TARGET_FIELDS,
    SEMANTIC_APPROVAL_FIELDS,
    SEMANTIC_BASE_FIELDS,
    SEMANTIC_DECISION_FIELDS,
)
from src.status_mapper import (
    is_final_status_group,
    is_negative_approval,
    is_pending_approval,
    is_positive_approval,
    normalize_approval_bucket,
    normalize_status,
)
from src.utils import (
    load_json,
    parse_date_like,
    parse_iso_datetime,
    safe_str,
    save_json,
    tokenize,
)


SOURCE_PRIORITY = {
    "xlsx": 2,
    "csv": 1,
}


def init_prepare_stats(raw_rows_total: int, rows_by_source: dict) -> dict:
    return {
        "rows_raw_total": raw_rows_total,
        "rows_by_source": rows_by_source,
        "rows_after_merge": 0,
        "rows_skipped_without_issue_id": 0,
        "date_parse_failures": 0,
        "placeholder_cleaning_counts": {},
        "semantic_noise_removed_counts": {},
        "source_conflicts_count": 0,
        "source_priority_used_count": 0,
    }


def bump_counter(stats: dict, bucket_name: str, key: str) -> None:
    bucket = stats.setdefault(bucket_name, {})
    bucket[key] = bucket.get(key, 0) + 1


def normalize_text_field(field_name: str, value, stats: dict) -> str:
    text = safe_str(value)
    if not text:
        return ""

    placeholders = EMPTY_PLACEHOLDERS_BY_TARGET.get(field_name, set())
    if text in placeholders:
        bump_counter(stats, "placeholder_cleaning_counts", field_name)

        if field_name in SEMANTIC_BASE_FIELDS or field_name in SEMANTIC_APPROVAL_FIELDS or field_name in SEMANTIC_DECISION_FIELDS:
            bump_counter(stats, "semantic_noise_removed_counts", field_name)

        return ""

    return text


def normalize_date_field(value, stats: dict) -> str:
    raw_text = safe_str(value)
    normalized = parse_date_like(value)

    if raw_text and not normalized:
        stats["date_parse_failures"] += 1

    return normalized


def filled_score(task: dict) -> int:
    return sum(1 for field in DEDUP_SCORE_FIELDS if safe_str(task.get(field)))


def compare_task_versions(current: dict, existing: dict, stats: dict) -> dict:
    current_updated = safe_str(current.get("updated_at"))
    existing_updated = safe_str(existing.get("updated_at"))

    if current_updated != existing_updated:
        return current if current_updated > existing_updated else existing

    current_score = filled_score(current)
    existing_score = filled_score(existing)

    if current_score != existing_score:
        stats["source_conflicts_count"] += 1
        return current if current_score > existing_score else existing

    current_source = SOURCE_PRIORITY.get(safe_str(current.get("source_type")), 0)
    existing_source = SOURCE_PRIORITY.get(safe_str(existing.get("source_type")), 0)

    if current_source != existing_source:
        stats["source_priority_used_count"] += 1
        return current if current_source > existing_source else existing

    return existing


def dedupe_tasks(tasks: list[dict], stats: dict) -> tuple[list[dict], dict]:
    by_id = {}
    duplicates = 0

    for task in tasks:
        issue_id = safe_str(task.get("issue_id"))
        if not issue_id:
            continue

        existing = by_id.get(issue_id)
        if existing is None:
            by_id[issue_id] = task
            continue

        duplicates += 1
        by_id[issue_id] = compare_task_versions(task, existing, stats)

    dedupe_stats = {
        "duplicates_removed": duplicates,
        "dedupe_groups_total": duplicates,
        "source_conflicts_count": stats.get("source_conflicts_count", 0),
        "source_priority_used_count": stats.get("source_priority_used_count", 0),
    }
    return list(by_id.values()), dedupe_stats


def collect_quality_issues(tasks: list[dict]) -> dict:
    missing = {field: 0 for field in REQUIRED_TARGET_FIELDS}

    for task in tasks:
        for field in REQUIRED_TARGET_FIELDS:
            if not safe_str(task.get(field)):
                missing[field] += 1

    return missing


def collect_unknown_statuses(tasks: list[dict]) -> list[str]:
    return sorted({
        t["raw_status"]
        for t in tasks
        if t.get("workflow_group") == "other" and t.get("raw_status")
    })


def compute_approval_snapshot(task: dict) -> dict:
    buckets = {
        "positive": 0,
        "pending": 0,
        "negative": 0,
        "mentioned": 0,
    }

    for field in APPROVAL_TARGET_FIELDS:
        value = safe_str(task.get(field))
        if not value:
            continue

        buckets["mentioned"] += 1

        if is_positive_approval(value):
            buckets["positive"] += 1
        elif is_pending_approval(value):
            buckets["pending"] += 1
        elif is_negative_approval(value):
            buckets["negative"] += 1

    return buckets


def compute_approval_details(task: dict) -> dict:
    """
    Возвращает:
    - список всех согласований с bucket
    - pending_approvals
    - current_approval_stage
    """
    items = []
    pending = []
    rejected = []

    for field in APPROVAL_TARGET_FIELDS:
        value = safe_str(task.get(field))
        if not value:
            continue

        label = APPROVAL_LABELS.get(field, field)
        bucket = normalize_approval_bucket(value)

        item = {
            "field": field,
            "label": label,
            "value": value,
            "bucket": bucket,
        }
        items.append(item)

        if bucket in {"review", "rework", "not_started"}:
            pending.append(label)

        if bucket == "rejected_or_cancelled":
            rejected.append(label)

    current_stage = ""
    for item in items:
        if item["bucket"] in {"review", "rework", "not_started"}:
            current_stage = item["label"]
            break

    if not current_stage and rejected:
        current_stage = rejected[0]

    return {
        "items": items,
        "pending_approvals": pending,
        "current_approval_stage": current_stage,
    }


def compute_deadline_entries(task: dict) -> list[dict]:
    items = []

    for field in DEADLINE_TARGET_FIELDS:
        value = safe_str(task.get(field))
        if not value:
            continue

        dt = parse_iso_datetime(value)
        if dt is None:
            continue

        items.append(
            {
                "field": field,
                "label": DEADLINE_LABELS.get(field, field),
                "value": value,
                "dt": dt,
            }
        )

    items.sort(key=lambda x: x["dt"])
    return items


def compute_deadline_snapshot(task: dict) -> dict:
    snapshot = {}
    for field in DEADLINE_TARGET_FIELDS:
        value = safe_str(task.get(field))
        if value:
            snapshot[field] = value
    return snapshot


def compute_is_final(task: dict) -> bool:
    if safe_str(task.get("resolved_at")):
        return True

    workflow_group = safe_str(task.get("workflow_group"))
    if workflow_group and is_final_status_group(workflow_group):
        return True

    raw_status = safe_str(task.get("raw_status"))
    if raw_status in {"Согласовано", "Согласовано с замеч.", "Отказано", "Согл. отменено"}:
        return True

    return False


def compute_main_deadline_fields(task: dict) -> dict:
    now = datetime.now()
    entries = compute_deadline_entries(task)

    if not entries:
        return {
            "deadline_entries": [],
            "main_deadline": {},
            "days_to_main_deadline": None,
            "is_overdue": False,
            "overdue_days": 0,
        }

    main = entries[0]
    delta_days = (main["dt"].date() - now.date()).days

    is_final = bool(task.get("is_final"))
    overdue_items = [x for x in entries if x["dt"].date() < now.date()]
    is_overdue = (not is_final) and bool(overdue_items)

    overdue_days = 0
    if is_overdue:
        overdue_days = max((now.date() - x["dt"].date()).days for x in overdue_items)

    serializable_entries = []
    for item in entries:
        serializable_entries.append(
            {
                "field": item["field"],
                "label": item["label"],
                "value": item["value"],
            }
        )

    serializable_main = {
        "field": main["field"],
        "label": main["label"],
        "value": main["value"],
    }

    return {
        "deadline_entries": serializable_entries,
        "main_deadline": serializable_main,
        "days_to_main_deadline": delta_days,
        "is_overdue": is_overdue,
        "overdue_days": overdue_days,
    }


def build_semantic_text(task: dict) -> str:
    """
    semantic_text — для embeddings и похожих задач.

    Здесь оставляем:
    - смысл постановки
    - ключевые approval-строки
    - осмысленные решения
    """
    lines = []

    for field in SEMANTIC_BASE_FIELDS:
        value = safe_str(task.get(field))
        if value:
            lines.append(value)

    for field in SEMANTIC_APPROVAL_FIELDS:
        value = safe_str(task.get(field))
        if value:
            label = APPROVAL_LABELS.get(field, field)
            lines.append(f"Согласование с {label}: {value}")

    decision_labels = {
        "decision_dit": "Решение ДИТ",
        "decision_gku": "Решение ГКУ",
        "decision_dkp": "Решение ДКП",
        "decision_dep": "Решение ДЭПиР",
    }

    for field in SEMANTIC_DECISION_FIELDS:
        value = safe_str(task.get(field))
        if value:
            lines.append(f"{decision_labels.get(field, field)}: {value}")

    return "\n".join(lines)


def build_metadata_text(task: dict) -> str:
    fields = [
        "issue_id",
        "project",
        "status",
        "raw_status",
        "status_group",
        "workflow_group",
        "priority",
        "doc_type",
        "functional_customer",
        "responsible_dit",
        "approval_initiator",
        "states_code",
        "created_at",
        "updated_at",
        "resolved_at",
        "deadline_dit",
        "deadline_gku",
        "deadline_dkp",
        "deadline_dep",
        "deadline_fix_comments",
        "initial_review_deadline",
        "current_approval_stage",
        "source_type",
        "source_file",
        "source_row",
    ]

    lines = []
    for field in fields:
        value = safe_str(task.get(field))
        if value:
            lines.append(f"{field}: {value}")

    pending = task.get("pending_approvals", [])
    if pending:
        lines.append("pending_approvals: " + ", ".join(pending))

    return "\n".join(lines)


def normalize_row(row, stats: dict) -> dict:
    task = {}

    for source_col, target_col in COLUMN_MAP.items():
        value = row.get(source_col)

        if target_col in DATE_TARGET_FIELDS:
            task[target_col] = normalize_date_field(value, stats)
        else:
            task[target_col] = normalize_text_field(target_col, value, stats)

    task["source_file"] = safe_str(row.get("__source_file"))
    task["source_path"] = safe_str(row.get("__source_path"))
    task["source_type"] = safe_str(row.get("__source_type"))
    task["source_row"] = safe_str(row.get("__source_row"))

    task["raw_status"] = safe_str(task.get("status"))
    task["status_group"] = normalize_status(task["status"])
    task["workflow_group"] = task["status_group"]

    task["is_final"] = compute_is_final(task)
    task["is_active"] = not task["is_final"]

    task["approval_snapshot"] = compute_approval_snapshot(task)

    approval_details = compute_approval_details(task)
    task["approval_details"] = approval_details["items"]
    task["pending_approvals"] = approval_details["pending_approvals"]
    task["current_approval_stage"] = approval_details["current_approval_stage"]

    task["deadlines"] = compute_deadline_snapshot(task)

    deadline_fields = compute_main_deadline_fields(task)
    task["deadline_entries"] = deadline_fields["deadline_entries"]
    task["main_deadline"] = deadline_fields["main_deadline"]
    task["days_to_main_deadline"] = deadline_fields["days_to_main_deadline"]
    task["is_overdue"] = deadline_fields["is_overdue"]
    task["overdue_days"] = deadline_fields["overdue_days"]

    task["semantic_text"] = build_semantic_text(task)
    task["metadata_text"] = build_metadata_text(task)
    task["tokens"] = tokenize(task["semantic_text"])
    task["has_description"] = bool(task["description"])

    return task


def build_tasks_dataset():
    df, files = load_source_dataframe()
    stats = init_prepare_stats(
        raw_rows_total=len(df),
        rows_by_source=files.get("rows_by_source", {}),
    )
    tasks = []

    for _, row in df.iterrows():
        issue_id = safe_str(row.get("ID задачи"))
        if not issue_id:
            stats["rows_skipped_without_issue_id"] += 1
            continue

        tasks.append(normalize_row(row, stats))

    stats["rows_after_merge"] = len(tasks)
    tasks, dedupe_stats = dedupe_tasks(tasks, stats)
    return tasks, files, stats, dedupe_stats


def build_dataset_report(tasks: list[dict], files: dict, stats: dict, dedupe_stats: dict) -> dict:
    status_counter = Counter(t["status"] for t in tasks if t["status"])
    raw_status_counter = Counter(t["raw_status"] for t in tasks if t.get("raw_status"))
    group_counter = Counter(t["status_group"] for t in tasks if t["status_group"])
    workflow_counter = Counter(t["workflow_group"] for t in tasks if t.get("workflow_group"))
    doc_type_counter = Counter(t["doc_type"] for t in tasks if t["doc_type"])
    priority_counter = Counter(t["priority"] for t in tasks if t["priority"])
    current_stage_counter = Counter(
        t["current_approval_stage"] for t in tasks if safe_str(t.get("current_approval_stage"))
    )

    with_description = sum(1 for t in tasks if t["has_description"])
    active_total = sum(1 for t in tasks if t.get("is_active"))
    final_total = sum(1 for t in tasks if t.get("is_final"))
    overdue_total = sum(1 for t in tasks if t.get("is_overdue"))
    with_pending_approvals = sum(1 for t in tasks if t.get("pending_approvals"))

    quality_missing_required = collect_quality_issues(tasks)
    unknown_statuses = collect_unknown_statuses(tasks)

    source_files = {
        "xlsx": [str(path) for path in files.get("xlsx", [])],
        "csv": [str(path) for path in files.get("csv", [])],
    }

    report = {
        "rows_raw_total": stats["rows_raw_total"],
        "rows_by_source": stats["rows_by_source"],
        "rows_after_merge": stats["rows_after_merge"],
        "rows_skipped_without_issue_id": stats["rows_skipped_without_issue_id"],
        "tasks_total_after_dedupe": len(tasks),
        "duplicates_removed": dedupe_stats["duplicates_removed"],
        "source_conflicts_count": dedupe_stats["source_conflicts_count"],
        "source_priority_used_count": dedupe_stats["source_priority_used_count"],
        "date_parse_failures": stats["date_parse_failures"],
        "placeholder_cleaning_counts": stats["placeholder_cleaning_counts"],
        "semantic_noise_removed_counts": stats["semantic_noise_removed_counts"],
        "source_files": source_files,
        "tasks_total": len(tasks),
        "active_total": active_total,
        "final_total": final_total,
        "overdue_total": overdue_total,
        "with_pending_approvals": with_pending_approvals,
        "with_description": with_description,
        "top_statuses": status_counter.most_common(20),
        "top_raw_statuses": raw_status_counter.most_common(20),
        "top_status_groups": group_counter.most_common(20),
        "top_workflow_groups": workflow_counter.most_common(20),
        "top_doc_types": doc_type_counter.most_common(10),
        "top_priorities": priority_counter.most_common(10),
        "top_current_approval_stages": current_stage_counter.most_common(10),
        "quality_missing_required": quality_missing_required,
        "unknown_statuses": unknown_statuses,
    }
    return report


def save_prepared_tasks():
    replacement_info = prepare_dataset_replacement_if_needed()

    tasks, files, stats, dedupe_stats = build_tasks_dataset()
    report = build_dataset_report(tasks, files, stats, dedupe_stats)

    save_json(tasks, TASKS_JSON)
    save_json(report, DATASET_REPORT_JSON)
    active_dataset = register_prepared_dataset(
        rows_raw_total=report["rows_raw_total"],
        tasks_total=len(tasks),
    )

    xlsx_names = ", ".join(path.name for path in files.get("xlsx", [])) or "нет"
    csv_names = ", ".join(path.name for path in files.get("csv", [])) or "нет"

    report_lines = [
        f"Источник XLSX: {xlsx_names}",
        f"Источник CSV: {csv_names}",
        f"Сырых строк всего: {report['rows_raw_total']}",
        f"Строк после объединения: {report['rows_after_merge']}",
        f"Всего задач после dedupe: {report['tasks_total_after_dedupe']}",
        f"Удалено дублей: {report['duplicates_removed']}",
        f"Активных задач: {report['active_total']}",
        f"Финальных задач: {report['final_total']}",
        f"Просроченных задач: {report['overdue_total']}",
        f"С задачами на согласовании: {report['with_pending_approvals']}",
        f"С описанием: {report['with_description']}",
        f"Ошибок парсинга дат: {report['date_parse_failures']}",
        f"Пустые обязательные поля: {report['quality_missing_required']}",
        f"Удаленные placeholder-значения: {report['placeholder_cleaning_counts']}",
        f"Топ сырых статусов: {report['top_raw_statuses'][:5]}",
        f"Топ workflow-групп: {report['top_workflow_groups'][:5]}",
        f"Топ текущих стадий согласования: {report['top_current_approval_stages'][:5]}",
        f"Неизвестные статусы: {report['unknown_statuses'][:10]}",
    ]

    report_lines.append(f"Active dataset_id: {active_dataset['dataset_id']}")

    if replacement_info.get("dataset_replaced"):
        report_lines.append("Замена датасета: да")

    if replacement_info.get("raw_removed"):
        report_lines.append(f"Очищены остатки old raw: {replacement_info['raw_removed']}")

    if replacement_info.get("processed_removed") or replacement_info.get("index_removed"):
        report_lines.append(
            "Очищены old processed/index: "
            f"{replacement_info.get('processed_removed', [])} / {replacement_info.get('index_removed', [])}"
        )

    return tasks, report_lines


def has_prepared_tasks() -> bool:
    if not TASKS_JSON.exists():
        return False

    try:
        tasks = load_json(TASKS_JSON)
    except Exception:
        return False

    return isinstance(tasks, list) and len(tasks) > 0
