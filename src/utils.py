import json
import math
import re
from pathlib import Path
from typing import Any
from datetime import datetime


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
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = str(value).strip()
    if text.lower() == "nan":
        return ""
    return text


def parse_date_like(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat(sep=" ", timespec="seconds")
        except TypeError:
            return value.isoformat()
    text = safe_str(value)
    if not text:
        return ""
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
