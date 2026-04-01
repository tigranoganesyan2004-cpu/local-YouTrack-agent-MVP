import sqlite3
import uuid

from src.config import SQLITE_HISTORY_FILE
from src.utils import ensure_dir, now_iso, safe_str


def _conn():
    return sqlite3.connect(SQLITE_HISTORY_FILE)


def _ensure_column(cur, table: str, column_name: str, column_type: str):
    cur.execute(f"PRAGMA table_info({table})")
    columns = {row[1] for row in cur.fetchall()}
    if column_name not in columns:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column_name} {column_type}")


def init_history_db():
    ensure_dir(SQLITE_HISTORY_FILE.parent)

    conn = _conn()
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

    _ensure_column(cur, "chat_history", "retrieved_candidates", "TEXT")
    _ensure_column(cur, "chat_history", "duration_ms", "INTEGER")
    _ensure_column(cur, "chat_history", "llm_used", "INTEGER")
    _ensure_column(cur, "chat_history", "error_text", "TEXT")
    _ensure_column(cur, "chat_history", "chat_id", "TEXT DEFAULT ''")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            dataset_id TEXT NOT NULL DEFAULT ''
        )
        """
    )
    _ensure_column(cur, "chat_sessions", "dataset_id", "TEXT DEFAULT ''")

    conn.commit()
    conn.close()


# ── chat session CRUD ────────────────────────────────────────────

def _is_archived_for_active_dataset(chat_dataset_id: str, active_dataset_id: str) -> bool:
    active_id = safe_str(active_dataset_id)
    if not active_id:
        return False
    return safe_str(chat_dataset_id) != active_id


def create_chat_session(title: str = "", dataset_id: str = "") -> dict:
    chat_id = uuid.uuid4().hex[:16]
    ts = now_iso()
    ds_id = safe_str(dataset_id)
    conn = _conn()
    conn.execute(
        "INSERT INTO chat_sessions (id, title, created_at, updated_at, dataset_id) VALUES (?, ?, ?, ?, ?)",
        (chat_id, title, ts, ts, ds_id),
    )
    conn.commit()
    conn.close()
    return {"id": chat_id, "title": title, "created_at": ts, "updated_at": ts, "dataset_id": ds_id}


def list_chat_sessions(limit: int = 50, active_dataset_id: str = "") -> list[dict]:
    conn = _conn()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, title, created_at, updated_at, dataset_id FROM chat_sessions ORDER BY updated_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()

    result = []
    for row in rows:
        item = dict(row)
        item["dataset_id"] = safe_str(item.get("dataset_id"))
        item["is_archived"] = _is_archived_for_active_dataset(item["dataset_id"], active_dataset_id)
        result.append(item)

    return result


def is_chat_session_live(chat_id: str, active_dataset_id: str) -> bool:
    chat_id = safe_str(chat_id)
    if not chat_id:
        return False

    conn = _conn()
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT dataset_id FROM chat_sessions WHERE id = ?",
        (chat_id,),
    ).fetchone()
    conn.close()

    if row is None:
        return False

    dataset_id = safe_str(row["dataset_id"])
    return not _is_archived_for_active_dataset(dataset_id, active_dataset_id)


def get_chat_messages(chat_id: str) -> list[dict]:
    conn = _conn()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, created_at, query_text, query_mode, answer_text,
               found_issue_ids, duration_ms, llm_used, error_text
        FROM chat_history
        WHERE chat_id = ?
        ORDER BY id ASC
        """,
        (chat_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_chat_session(chat_id: str) -> bool:
    conn = _conn()
    conn.execute("DELETE FROM chat_history WHERE chat_id = ?", (chat_id,))
    cur = conn.execute("DELETE FROM chat_sessions WHERE id = ?", (chat_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def update_chat_session_title(chat_id: str, title: str) -> bool:
    conn = _conn()
    cur = conn.execute(
        "UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ?",
        (title, now_iso(), chat_id),
    )
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


def _touch_chat_session(chat_id: str) -> None:
    if not chat_id:
        return
    conn = _conn()
    conn.execute(
        "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
        (now_iso(), chat_id),
    )
    conn.commit()
    conn.close()


# ── history (backward-compatible) ────────────────────────────────

def save_history(
    query_text: str,
    query_mode: str,
    answer_text: str,
    found_issue_ids: str,
    retrieved_candidates: str = "",
    duration_ms: int = 0,
    llm_used: int = 0,
    error_text: str = "",
    chat_id: str = "",
):
    conn = _conn()
    conn.execute(
        """
        INSERT INTO chat_history (
            created_at, query_text, query_mode, answer_text, found_issue_ids,
            retrieved_candidates, duration_ms, llm_used, error_text, chat_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            now_iso(), query_text, query_mode, answer_text, found_issue_ids,
            retrieved_candidates, duration_ms, llm_used, error_text, chat_id,
        ),
    )
    conn.commit()
    conn.close()
    _touch_chat_session(chat_id)


def get_last_history(limit: int = 10):
    conn = _conn()
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
