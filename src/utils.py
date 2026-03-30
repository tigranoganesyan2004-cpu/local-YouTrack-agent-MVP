import json
import math
import re
from pathlib import Path
from typing import Any
from datetime import datetime

import pandas as pd


EMPTY_TEXT_VALUES = {"", "nan", "nat", "none", "null", "n/a"}


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def save_json(data: Any, path: Path) -> None:
    ensure_dir(path.parent)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def safe_str(value: Any) -> str:
    """
    Безопасно превращает значение в строку.

    Пустыми считаем:
    - None
    - NaN / NaT
    - строки "nan", "nat", "none", "null"
    - пустые строки и строки из пробелов
    """
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    if isinstance(value, float) and math.isnan(value):
        return ""

    text = str(value).strip()
    if text.lower() in EMPTY_TEXT_VALUES:
        return ""
    return text


DATE_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
    "%d %b %Y",
    "%d %b %Y %H:%M:%S",
    "%Y-%m-%d",
]


def parse_date_like(value: Any) -> str:
    """
    Приводит любые даты к формату:
    YYYY-MM-DD HH:MM:SS

    Поддерживает:
    - pandas.Timestamp / datetime
    - строки из CSV вида "26 Mar 2026"
    - ISO-строки
    """
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    if hasattr(value, "strftime") and not isinstance(value, str):
        try:
            return value.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

    text = safe_str(value)
    if not text:
        return ""

    for fmt in DATE_FORMATS:
        try:
            dt = datetime.strptime(text, fmt)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue

    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return ""

    if isinstance(parsed, pd.Timestamp):
        return parsed.to_pydatetime().strftime("%Y-%m-%d %H:%M:%S")

    try:
        return parsed.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def parse_iso_datetime(value: Any):
    """
    Возвращает datetime или None.
    Используем уже после normalize/prepare.
    """
    text = safe_str(value)
    if not text:
        return None

    try:
        return datetime.fromisoformat(text.replace("T", " "))
    except ValueError:
        return None


def clean_column_name(name: Any) -> str:
    """
    Нормализует заголовок колонки:
    - снимает BOM
    - убирает внешние кавычки
    - убирает лишние пробелы

    Пример:
    '\ufeff"ID задачи"' -> 'ID задачи'
    """
    text = safe_str(name)
    if not text:
        return ""

    text = text.lstrip("\ufeff")

    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1]

    text = normalize_space(text)
    return text


def normalize_space(text: str) -> str:
    text = safe_str(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def tokenize(text: str) -> list[str]:
    text = normalize_space(text).lower()
    tokens = re.findall(r"[a-zа-яё0-9_]+", text, flags=re.IGNORECASE)
    return [t for t in tokens if len(t) >= 2]


def truncate(text: str, max_chars: int) -> str:
    text = safe_str(text)
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")