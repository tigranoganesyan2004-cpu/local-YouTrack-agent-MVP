import sqlite3

from src.config import SQLITE_HISTORY_FILE
from src.utils import ensure_dir, now_iso


def _ensure_column(cur, table: str, column_name: str, column_type: str):
    cur.execute(f"PRAGMA table_info({table})")
    columns = {row[1] for row in cur.fetchall()}
    if column_name not in columns:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column_name} {column_type}")


def init_history_db():
    ensure_dir(SQLITE_HISTORY_FILE.parent)

    conn = sqlite3.connect(SQLITE_HISTORY_FILE)
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            query_text TEXT,
            query_mode TEXT,
            answer_text TEXT,
            found_issue_ids TEXT
        )
        """
    )

    # Мягкая миграция старой таблицы под Stage 1+
    _ensure_column(cur, "chat_history", "retrieved_candidates", "TEXT")
    _ensure_column(cur, "chat_history", "duration_ms", "INTEGER")
    _ensure_column(cur, "chat_history", "llm_used", "INTEGER")
    _ensure_column(cur, "chat_history", "error_text", "TEXT")

    conn.commit()
    conn.close()


def save_history(
    query_text: str,
    query_mode: str,
    answer_text: str,
    found_issue_ids: str,
    retrieved_candidates: str = "",
    duration_ms: int = 0,
    llm_used: int = 0,
    error_text: str = "",
):
    conn = sqlite3.connect(SQLITE_HISTORY_FILE)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO chat_history (
            created_at, query_text, query_mode, answer_text, found_issue_ids,
            retrieved_candidates, duration_ms, llm_used, error_text
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            now_iso(), query_text, query_mode, answer_text, found_issue_ids,
            retrieved_candidates, duration_ms, llm_used, error_text
        ),
    )
    conn.commit()
    conn.close()


def get_last_history(limit: int = 10):
    conn = sqlite3.connect(SQLITE_HISTORY_FILE)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT created_at, query_mode, query_text, answer_text, found_issue_ids, duration_ms, llm_used, error_text
        FROM chat_history
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows