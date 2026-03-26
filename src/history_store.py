import sqlite3

from src.config import SQLITE_HISTORY_FILE
from src.utils import ensure_dir, now_iso


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
    conn.commit()
    conn.close()


def save_history(query_text: str, query_mode: str, answer_text: str, found_issue_ids: str):
    conn = sqlite3.connect(SQLITE_HISTORY_FILE)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO chat_history (created_at, query_text, query_mode, answer_text, found_issue_ids)
        VALUES (?, ?, ?, ?, ?)
        """,
        (now_iso(), query_text, query_mode, answer_text, found_issue_ids),
    )
    conn.commit()
    conn.close()


def get_last_history(limit: int = 10):
    conn = sqlite3.connect(SQLITE_HISTORY_FILE)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT created_at, query_mode, query_text, answer_text, found_issue_ids
        FROM chat_history
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows
