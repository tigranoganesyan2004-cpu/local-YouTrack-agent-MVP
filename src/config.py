from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
INDEX_DIR = DATA_DIR / "index"
HISTORY_DIR = DATA_DIR / "history"

TASKS_JSON = PROCESSED_DIR / "tasks.json"
DATASET_REPORT_JSON = PROCESSED_DIR / "dataset_report.json"
FAISS_INDEX_FILE = INDEX_DIR / "tasks.index"
FAISS_MAPPING_FILE = INDEX_DIR / "tasks_mapping.json"
SQLITE_HISTORY_FILE = HISTORY_DIR / "agent_history.db"

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
GEN_MODEL = os.getenv("GEN_MODEL", "qwen2.5:3b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")

YOUTRACK_BASE_URL = os.getenv("YOUTRACK_BASE_URL", "").rstrip("/")
YOUTRACK_TOKEN = os.getenv("YOUTRACK_TOKEN", "")
YOUTRACK_PROJECT = os.getenv("YOUTRACK_PROJECT", "")

# Re-ranking через CrossEncoder.
# Отключить: добавить USE_RERANKER=false в .env
USE_RERANKER: bool = os.getenv("USE_RERANKER", "true").strip().lower() != "false"

# -------------------------------------------------------------------
# LLM-heavy режим
# -------------------------------------------------------------------
# FAST — обычный LLM-анализ
# DEEP — расширенный контекст и более тяжелый grounded analysis

FAST_ANALYSIS_TOP_K = int(os.getenv("FAST_ANALYSIS_TOP_K", "8"))
DEEP_ANALYSIS_TOP_K = int(os.getenv("DEEP_ANALYSIS_TOP_K", "16"))

MAX_CONTEXT_TASKS_FAST = int(os.getenv("MAX_CONTEXT_TASKS_FAST", "8"))
MAX_CONTEXT_TASKS_DEEP = int(os.getenv("MAX_CONTEXT_TASKS_DEEP", "16"))

MAX_TEXT_CHARS_FAST = int(os.getenv("MAX_TEXT_CHARS_FAST", "800"))
MAX_TEXT_CHARS_DEEP = int(os.getenv("MAX_TEXT_CHARS_DEEP", "1400"))

# Оставляем старые имена для обратной совместимости
MAX_CONTEXT_TASKS = MAX_CONTEXT_TASKS_FAST
MAX_TEXT_CHARS = MAX_TEXT_CHARS_DEEP