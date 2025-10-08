import json
import os
import sqlite3
import time
from contextlib import suppress
from typing import Any

# --- Paths helpers -----------------------------------------------------------


def _resolve_paths() -> tuple[str, str]:
    """
    Returns (task_db_path, task_log_path).

    Behavior:
      - If TASK_DB is set, we log next to it (same dir), unless TASK_LOG overrides.
      - Else, we use DATA_DIR (if set), else "data/pointers".
      - TASK_LOG, if set, always wins for the log file.
    """
    # default DB dir
    default_dir = os.path.join("data", "pointers")

    task_db = os.environ.get("TASK_DB")
    if task_db:
        base_dir = os.path.dirname(task_db) or default_dir
    else:
        base_dir = os.environ.get("DATA_DIR") or default_dir
        task_db = os.path.join(base_dir, "tasks.db")

    task_log = os.environ.get("TASK_LOG") or os.path.join(base_dir, "tasks.log")
    return task_db, task_log


# --- JSONL append ------------------------------------------------------------


def _append_jsonl(task: dict[str, Any]) -> None:
    _, log = _resolve_paths()
    os.makedirs(os.path.dirname(log), exist_ok=True)  # will be writable in tests
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(task, ensure_ascii=False) + "\n")


# --- Public API used by app --------------------------------------------------


def append_task(task: dict[str, Any]) -> None:
    """
    Append to JSONL and optionally persist to sqlite if TASK_DB exists/needed.
    Handles both schemas:
      - legacy: tasks(id, task, payload)
      - new:    tasks(id, ts, task, payload) with ts NOT NULL
    """
    _append_jsonl(task)

    db_path, _ = _resolve_paths()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()

        # Create table (new schema) if missing
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                task TEXT NOT NULL,
                payload TEXT
            )
            """
        )

        # Detect columns actually present (table may already exist with/without ts)
        cur.execute("PRAGMA table_info(tasks)")
        cols = {row[1] for row in cur.fetchall()}  # row[1] is column name

        payload_json = json.dumps(task.get("payload") or {})
        if "ts" in cols:
            cur.execute(
                "INSERT INTO tasks (ts, task, payload) VALUES (?, ?, ?)",
                (time.time(), task.get("task"), payload_json),
            )
        else:
            # Fallback for legacy schema that didn't have ts
            cur.execute(
                "INSERT INTO tasks (task, payload) VALUES (?, ?)",
                (task.get("task"), payload_json),
            )

        conn.commit()
    finally:
        conn.close()


def recent_tasks(limit: int = 50) -> list[dict[str, Any]]:
    db_path, _ = _resolve_paths()
    if not os.path.exists(db_path):
        return []

    out: list[dict[str, Any]] = []
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT task, payload FROM tasks ORDER BY id DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        for task_name, payload_json in rows:
            payload: Any = None
            with suppress(Exception):
                payload = json.loads(payload_json) if payload_json else None
            out.append({"task": task_name, "payload": payload})
    finally:
        conn.close()
    return out
