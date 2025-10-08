# tests/unit/test_store_ts_compat.py
from __future__ import annotations

import sqlite3

from services.app_server.store import append_task


def _rows(conn: sqlite3.Connection, q: str) -> list[tuple]:
    cur = conn.cursor()
    cur.execute(q)
    return cur.fetchall()


def test_append_task_without_ts_column(tmp_path, monkeypatch):
    """
    When the 'tasks' table has no 'ts' column, append_task() should still insert rows.
    """
    db_path = tmp_path / "jobs_no_ts.db"
    log_path = tmp_path / "tasks.log"

    monkeypatch.setenv("TASK_DB", str(db_path))
    monkeypatch.setenv("TASK_LOG", str(log_path))

    # Pre-create DB with a minimal schema (no ts column).
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task TEXT NOT NULL,
                payload TEXT
            );
            """
        )
        conn.commit()
    finally:
        conn.close()

    # Insert via the code under test
    append_task({"task": "plan", "payload": {"ok": True}})

    conn = sqlite3.connect(db_path)
    try:
        rows = _rows(conn, "SELECT id, task, payload FROM tasks;")
        assert len(rows) == 1
        _id, task, payload = rows[0]
        assert task == "plan"
        assert payload is not None and '"ok": true' in payload
    finally:
        conn.close()

    # JSONL file should also exist
    assert log_path.exists()
    assert log_path.read_text().strip() != ""


def test_append_task_with_ts_column(tmp_path, monkeypatch):
    """
    When the 'tasks' table includes a NOT NULL ts column, append_task() must populate it.
    """
    db_path = tmp_path / "jobs_with_ts.db"
    log_path = tmp_path / "tasks.log"

    monkeypatch.setenv("TASK_DB", str(db_path))
    monkeypatch.setenv("TASK_LOG", str(log_path))

    # Pre-create DB with a strict ts column (NOT NULL).
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task TEXT NOT NULL,
                payload TEXT,
                ts INTEGER NOT NULL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()

    # Insert via the code under test
    append_task({"task": "plan", "payload": {"i": 1}})

    conn = sqlite3.connect(db_path)
    try:
        rows = _rows(conn, "SELECT id, task, payload, ts FROM tasks;")
        assert len(rows) == 1
        _id, task, payload, ts = rows[0]
        assert task == "plan"
        assert payload is not None and '"i": 1' in payload
        assert isinstance(ts, int)
        assert ts > 0
    finally:
        conn.close()

    # JSONL file should also exist
    assert log_path.exists()
    assert log_path.read_text().strip() != ""
