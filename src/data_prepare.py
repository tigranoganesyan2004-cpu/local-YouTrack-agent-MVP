from collections import Counter

from src.data_loader import load_source_dataframe
from src.schema import COLUMN_MAP
from src.status_mapper import normalize_status
from src.utils import safe_str, parse_date_like, save_json, load_json, tokenize
from src.config import TASKS_JSON, DATASET_REPORT_JSON


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

DEADLINE_FIELDS = [
    "deadline_dit",
    "deadline_gku",
    "deadline_dkp",
    "deadline_dep",
    "deadline_fix_comments",
]

REQUIRED_FIELDS = ["issue_id", "summary", "status", "doc_type"]


def dedupe_tasks(tasks: list[dict]) -> tuple[list[dict], int]:
    """
    Удаляет дубли по issue_id.

    Логика:
    - если задача встретилась один раз, просто сохраняем;
    - если встретилась повторно, оставляем ту версию,
      у которой updated_at новее.

    Возвращаем:
    - список очищенных задач
    - сколько дублей было удалено
    """
    by_id = {}
    duplicates = 0

    for task in tasks:
        issue_id = task.get("issue_id", "")
        if not issue_id:
            continue

        existing = by_id.get(issue_id)
        if existing is None:
            by_id[issue_id] = task
            continue

        duplicates += 1

        current_updated = task.get("updated_at") or ""
        existing_updated = existing.get("updated_at") or ""

        # Оставляем более новую версию задачи.
        # Сравнение строк работает нормально, если даты уже приведены
        # к единому ISO-подобному формату.
        if current_updated >= existing_updated:
            by_id[issue_id] = task

    return list(by_id.values()), duplicates


def collect_quality_issues(tasks: list[dict]) -> dict:
    """
    Считает, сколько задач имеют пустые обязательные поля.

    Это нужно, чтобы в dataset_report.json сразу видеть качество выгрузки.
    """
    missing = {field: 0 for field in REQUIRED_FIELDS}

    for task in tasks:
        for field in REQUIRED_FIELDS:
            if not safe_str(task.get(field)):
                missing[field] += 1

    return missing


def collect_unknown_statuses(tasks: list[dict]) -> list[str]:
    """
    Возвращает все сырые статусы, которые не были распознаны
    и попали в группу other.

    Это главный контрольный список для донастройки status map.
    """
    return sorted({
        t["raw_status"]
        for t in tasks
        if t.get("workflow_group") == "other" and t.get("raw_status")
    })

def build_semantic_text(task: dict) -> str:
    """
    semantic_text — это только смысл задачи для embeddings.

    Здесь НЕ должно быть служебного шума:
    - статуса
    - приоритета
    - заказчика
    - ответственного
    - дедлайнов

    Иначе модель начнет находить задачи по фильтровым полям,
    а не по содержанию постановки.
    """
    parts = [
        task.get("summary", ""),
        task.get("description", ""),
        task.get("action", ""),
        task.get("decision_dit", ""),
        task.get("decision_gku", ""),
        task.get("decision_dkp", ""),
        task.get("decision_dep", ""),
    ]

    clean = []
    for x in parts:
        value = safe_str(x)
        if not value:
            continue
        if value == "Не выбран":
            continue
        clean.append(value)

    return "\n".join(clean)

def build_metadata_text(task: dict) -> str:
    """
    metadata_text — это служебный слой для фильтров, lexical поиска,
    карточки и диагностического контекста.

    В отличие от semantic_text, здесь как раз должны быть:
    - статус
    - группа статуса
    - тип документа
    - заказчик
    - ответственный
    - сроки
    """
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
        "created_at",
        "updated_at",
        "resolved_at",
        "deadline_dit",
        "deadline_gku",
        "deadline_dkp",
        "deadline_dep",
        "deadline_fix_comments",
    ]

    lines = []
    for field in fields:
        value = safe_str(task.get(field))
        if value:
            lines.append(f"{field}: {value}")

    return "\n".join(lines)

def compute_approval_snapshot(task: dict) -> dict:
    positive = 0
    pending = 0
    negative = 0
    mentioned = 0

    for field in APPROVAL_FIELDS:
        value = safe_str(task.get(field)).strip().lower()
        if not value:
            continue
        mentioned += 1
        if "согласовано" in value:
            positive += 1
        elif "направлено" in value:
            pending += 1
        elif "отказ" in value or "замеч" in value or "отмен" in value:
            negative += 1

    return {
        "positive": positive,
        "pending": pending,
        "negative": negative,
        "mentioned": mentioned,
    }


def compute_deadline_snapshot(task: dict) -> dict:
    non_empty = {}
    for field in DEADLINE_FIELDS:
        value = safe_str(task.get(field))
        if value:
            non_empty[field] = value
    return non_empty


def normalize_row(row) -> dict:
    """
    Преобразует строку исходной выгрузки в единый внутренний объект задачи.

    Важная идея:
    - status хранится как человекочитаемое сырое значение;
    - raw_status дублирует его явно для будущей логики Stage 2;
    - status_group оставляем для обратной совместимости;
    - workflow_group вводим как основной логический статус на будущее.
    """
    task = {}

    for source_col, target_col in COLUMN_MAP.items():
        value = row.get(source_col)

        if target_col in {
            "created_at", "updated_at", "resolved_at",
            "start_dit", "start_gku", "start_dkp", "start_dep",
            "deadline_dit", "deadline_dkp", "deadline_dep", "deadline_gku",
            "deadline_fix_comments",
        }:
            task[target_col] = parse_date_like(value)
        else:
            task[target_col] = safe_str(value)

    # Явно сохраняем сырой статус как отдельное поле.
    # Это пригодится для Stage 2 и диагностики новых статусов.
    task["raw_status"] = safe_str(task.get("status"))

    # Сохраняем старое поле status_group, чтобы не ломать текущий Stage 1.
    task["status_group"] = normalize_status(task["status"])

    # Новое поле: рабочая группа процесса согласования.
    # По сути сейчас оно совпадает со status_group,
    # но дальше именно workflow_group станет главным логическим полем.
    task["workflow_group"] = task["status_group"]

    task["approval_snapshot"] = compute_approval_snapshot(task)
    task["deadlines"] = compute_deadline_snapshot(task)
    task["semantic_text"] = build_semantic_text(task)
    task["metadata_text"] = build_metadata_text(task)
    task["tokens"] = tokenize(task["semantic_text"])
    task["has_description"] = bool(task["description"])
    return task

def build_tasks_dataset():
    """
    Загружает исходные данные, нормализует каждую строку
    и затем удаляет дубли по issue_id.
    """
    df, files = load_source_dataframe()
    tasks = []

    for _, row in df.iterrows():
        issue_id = safe_str(row.get("ID задачи"))
        if not issue_id:
            continue
        tasks.append(normalize_row(row))

    tasks, duplicates = dedupe_tasks(tasks)
    return tasks, files, duplicates

def build_dataset_report(tasks: list[dict], files: dict, duplicates: int) -> dict:
    """
    Диагностический отчет по датасету после подготовки.

    Здесь важно видеть:
    - сколько задач;
    - сколько дублей удалено;
    - какие статусы реально встретились;
    - как они распределились по workflow_group;
    - какие статусы ушли в other.
    """
    status_counter = Counter(t["status"] for t in tasks if t["status"])
    raw_status_counter = Counter(t["raw_status"] for t in tasks if t.get("raw_status"))
    group_counter = Counter(t["status_group"] for t in tasks if t["status_group"])
    workflow_counter = Counter(t["workflow_group"] for t in tasks if t.get("workflow_group"))
    doc_type_counter = Counter(t["doc_type"] for t in tasks if t["doc_type"])
    priority_counter = Counter(t["priority"] for t in tasks if t["priority"])
    with_description = sum(1 for t in tasks if t["has_description"])

    quality_missing_required = collect_quality_issues(tasks)
    unknown_statuses = collect_unknown_statuses(tasks)

    report = {
        "tasks_total": len(tasks),
        "duplicates_removed": duplicates,
        "with_description": with_description,
        "source_files": {k: str(v) if v else "" for k, v in files.items()},
        "top_statuses": status_counter.most_common(20),
        "top_raw_statuses": raw_status_counter.most_common(20),
        "top_status_groups": group_counter.most_common(20),
        "top_workflow_groups": workflow_counter.most_common(20),
        "top_doc_types": doc_type_counter.most_common(10),
        "top_priorities": priority_counter.most_common(10),
        "quality_missing_required": quality_missing_required,
        "unknown_statuses": unknown_statuses,
    }
    return report

def save_prepared_tasks():
    """
    Полный pipeline подготовки:
    - загрузка,
    - нормализация,
    - дедупликация,
    - отчет качества,
    - сохранение tasks.json и dataset_report.json.
    """
    tasks, files, duplicates = build_tasks_dataset()
    report = build_dataset_report(tasks, files, duplicates)

    save_json(tasks, TASKS_JSON)
    save_json(report, DATASET_REPORT_JSON)

    report_lines = [
        f"Источник XLSX: {files['xlsx'].name if files['xlsx'] else 'нет'}",
        f"Источник CSV: {files['csv'].name if files['csv'] else 'нет'}",
        f"Всего задач: {report['tasks_total']}",
        f"Удалено дублей: {report['duplicates_removed']}",
        f"С описанием: {report['with_description']}",
        f"Топ сырых статусов: {report['top_raw_statuses'][:5]}",
        f"Топ workflow-групп: {report['top_workflow_groups'][:5]}",
        f"Пустые обязательные поля: {report['quality_missing_required']}",
        f"Неизвестные статусы: {report['unknown_statuses'][:10]}",
    ]
    return tasks, report_lines

def has_prepared_tasks() -> bool:
    """
    Проверяет, готовы ли подготовленные данные для работы агента.

    Условия:
    - tasks.json существует
    - внутри лежит список
    - список не пустой
    """
    if not TASKS_JSON.exists():
        return False

    try:
        tasks = load_json(TASKS_JSON)
    except Exception:
        return False

    return isinstance(tasks, list) and len(tasks) > 0