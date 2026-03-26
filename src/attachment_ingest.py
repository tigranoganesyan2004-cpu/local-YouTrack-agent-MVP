from pathlib import Path
from src.utils import safe_str

ATTACHMENTS_DIR_NAME = "attachments"


def discover_issue_attachments(base_dir: Path, issue_id: str) -> list[Path]:
    issue_dir = base_dir / ATTACHMENTS_DIR_NAME / issue_id
    if not issue_dir.exists():
        return []
    return sorted([p for p in issue_dir.rglob("*") if p.is_file()])


def extract_text_stub(path: Path) -> str:
    """    Заглушка.
    На следующем этапе сюда добавляется реальное извлечение текста:
    - txt / md / json / csv;
    - docx;
    - pdf;
    - изображения через OCR (если потребуется).

    В текущем MVP вложения еще не участвуют.
    """
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".json", ".csv"}:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""
    return ""
