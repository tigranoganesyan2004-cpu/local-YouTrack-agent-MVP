from src.utils import safe_str


STATUS_TO_WORKFLOW = {
    "Согласовано": "approved",
    "Согласовано с замеч.": "approved_with_remarks",
    "Направлено на согл.": "review",
    "Выданы замечания": "rework",
    "Отказано": "rejected_or_cancelled",
    "Согл. отменено": "rejected_or_cancelled",
    "Согл. не инициировано": "not_started",
    "Согл. не требуется": "not_required",
}


def normalize_raw_status(raw_status: str) -> str:
    return safe_str(raw_status).strip()


def normalize_status(raw_status: str) -> str:
    status = normalize_raw_status(raw_status)
    return STATUS_TO_WORKFLOW.get(status, "other")


def is_final_status_group(status_group: str) -> bool:
    """
    Финальные группы процесса:
    - approved
    - approved_with_remarks
    - rejected_or_cancelled
    - not_required
    """
    return safe_str(status_group) in {
        "approved",
        "approved_with_remarks",
        "rejected_or_cancelled",
        "not_required",
    }


def normalize_approval_bucket(value: str) -> str:
    """
    Нормализует статус отдельного согласования по ведомству.
    """
    raw = normalize_raw_status(value)
    return STATUS_TO_WORKFLOW.get(raw, "other")


def is_pending_approval(value: str) -> bool:
    return normalize_approval_bucket(value) in {"review", "rework", "not_started"}


def is_positive_approval(value: str) -> bool:
    return normalize_approval_bucket(value) in {
        "approved",
        "approved_with_remarks",
        "not_required",
    }


def is_negative_approval(value: str) -> bool:
    return normalize_approval_bucket(value) == "rejected_or_cancelled"