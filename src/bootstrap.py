from src.config import DATA_DIR, RAW_DIR, PROCESSED_DIR, INDEX_DIR, HISTORY_DIR
from src.utils import ensure_dir


def bootstrap_project():
    for path in [DATA_DIR, RAW_DIR, PROCESSED_DIR, INDEX_DIR, HISTORY_DIR]:
        ensure_dir(path)
