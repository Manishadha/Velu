# services/queue/sqlite_queue.py
from __future__ import annotations

import json
import os
import random
import sqlite3
import time
from contextlib import contextmanager
from typing import Any


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


SQLQ_MAX_ATTEMPTS = _int_env("SQLQ_MAX_ATTEMPTS", 3)
SQLQ_RETRY_BASE_SEC = _int_env("SQLQ_RETRY_BASE_SEC", 2)


def _db_path() -> str:
    task_db = os.getenv("TASK_DB")
    if task_db:
        return task_db
    task_log = os.getenv("TASK_LOG")
    if task_log:
        base = os.path.dirname(task_log) or "."
        return os.path.join(base, "jobs.db")
    return os.path.join("data", "jobs.db")


DDL_JOBS = """
CREATE TABLE IF NOT EXISTS jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task        TEXT NOT NULL,
    payload     TEXT,
    status      TEXT NOT NULL DEFAULT 'queued',
    result      TEXT
);
"""

_OPTIONAL_COLS = {
    "attempts": "ALTER TABLE jobs ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;",
    "next_run_at": "ALTER TABLE jobs ADD COLUMN next_run_at INTEGER;",
    "priority": "ALTER TABLE jobs ADD COLUMN priority INTEGER NOT NULL DEFAULT 0;",
    "last_error": "ALTER TABLE jobs ADD COLUMN last_error TEXT;",
}


def _safe_add_column(con: sqlite3.Connection, name: str, ddl: str) -> None:
    try:
        con.execute(ddl)
    except sqlite3.OperationalError as e:
        msg = str(e).lower()
        if "duplicate" in msg or "already exists" in msg:
            return
        raise


def _migrate(con: sqlite3.Connection) -> None:
    con.execute(DDL_JOBS)
    cols = {row[1] for row in con.execute("PRAGMA table_info(jobs)")}
    for col, ddl in _OPTIONAL_COLS.items():
        if col not in cols:
            _safe_add_column(con, col, ddl)
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_ready " "ON jobs(status, next_run_at, priority, id)"
    )


@contextmanager
def _conn():
    path = _db_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    con = sqlite3.connect(path, timeout=30, check_same_thread=False)
    try:
        try:
            con.execute("PRAGMA journal_mode=WAL;")
            con.execute("PRAGMA synchronous=NORMAL;")
            con.execute("PRAGMA foreign_keys=ON;")
        except sqlite3.OperationalError:
            pass
        _migrate(con)
        con.commit()
        yield con
    finally:
        con.close()


def init() -> None:
    with _conn():
        pass


def _now() -> int:
    return int(time.time())


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_loads_maybe(s: str | None) -> Any:
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return s


def _normalize_result_for_storage(result: Any) -> str:
    if isinstance(result, (bytes, bytearray)):
        result = result.decode("utf-8", errors="replace")
    if isinstance(result, str):
        try:
            json.loads(result)
            return result
        except Exception:
            return _json_dumps({"ok": True, "data": result})
    return _json_dumps(result)


def _next_delay(attempts: int) -> int:
    exp = max(0, attempts)
    base = max(1, SQLQ_RETRY_BASE_SEC)
    delay = base * (2**exp)
    jitter = random.uniform(0, 0.25 * delay)  # nosec B311
    return int(delay + jitter)


def enqueue(
    item: Any = None,
    *,
    task: str | None = None,
    payload: dict[str, Any] | None = None,
    key: str | None = None,
    priority: int = 0,
    not_before: int | None = None,
) -> int:
    if isinstance(item, dict) and task is None and payload is None:
        task = str(item.get("task", ""))
        payload = item.get("payload") or {}
    else:
        task = str(task or "")
        payload = payload or {}
    if not task:
        raise ValueError("enqueue: 'task' must be provided")
    payload_json = _json_dumps(payload)
    with _conn() as con:
        cur = con.execute(
            """
            INSERT INTO jobs(task, payload, status, priority, next_run_at, attempts)
            VALUES(?,?,?,?,?,?)
            """,
            (
                task,
                payload_json,
                "queued",
                int(priority),
                int(not_before) if not_before else None,
                0,
            ),
        )
        con.commit()
        return int(cur.lastrowid)


def dequeue() -> int | None:
    with _conn() as con:
        con.execute("BEGIN IMMEDIATE")
        now = _now()
        row = con.execute(
            """
            SELECT id FROM jobs
            WHERE status='queued'
              AND (next_run_at IS NULL OR next_run_at <= ?)
            ORDER BY priority DESC, id
            LIMIT 1
            """,
            (now,),
        ).fetchone()
        if not row:
            con.execute("COMMIT")
            return None
        job_id = int(row[0])
        updated = con.execute(
            "UPDATE jobs SET status='in_progress' WHERE id=? AND status='queued'",
            (job_id,),
        )
        if updated.rowcount == 0:
            con.execute("COMMIT")
            return None
        con.commit()
        return job_id


def load(job_id: int) -> dict[str, Any]:
    with _conn() as con:
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        return {}
    keys = row.keys()
    return {
        "id": row["id"],
        "task": row["task"],
        "payload": _json_loads_maybe(row["payload"]) or {},
        "status": row["status"],
        "result": _json_loads_maybe(row["result"]),
        "attempts": row["attempts"] if "attempts" in keys else 0,
        "priority": row["priority"] if "priority" in keys else 0,
        "next_run_at": row["next_run_at"] if "next_run_at" in keys else None,
        "last_error": row["last_error"] if "last_error" in keys else None,
    }


def finish(job_id: int, result: Any) -> None:
    with _conn() as con:
        result_json = _normalize_result_for_storage(result)
        con.execute(
            """
            UPDATE jobs
               SET status='done',
                   result=?,
                   next_run_at=NULL
             WHERE id=?
            """,
            (result_json, job_id),
        )
        con.commit()


def fail(job_id: int, message: str) -> None:
    with _conn() as con:
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT attempts FROM jobs WHERE id=?", (job_id,)).fetchone()
        attempts = int(row["attempts"]) if row else 0
        new_attempts = attempts + 1
        terminal = new_attempts >= max(1, SQLQ_MAX_ATTEMPTS)
        err_payload = {"ok": False, "error": str(message), "attempts": new_attempts}
        if terminal:
            con.execute(
                """
                UPDATE jobs
                   SET status='error',
                       result=?,
                       attempts=?,
                       last_error=?,
                       next_run_at=NULL
                 WHERE id=?
                """,
                (_json_dumps(err_payload), new_attempts, str(message), job_id),
            )
        else:
            delay = _next_delay(attempts)
            con.execute(
                """
                UPDATE jobs
                   SET status='queued',
                       attempts=?,
                       last_error=?,
                       next_run_at=?
                 WHERE id=?
                """,
                (new_attempts, str(message), _now() + delay, job_id),
            )
        con.commit()


def list_recent(limit: int = 50) -> list[dict[str, Any]]:
    with _conn() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM jobs ORDER BY id DESC LIMIT ?",
            (max(1, limit),),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        keys = r.keys()
        out.append(
            {
                "id": r["id"],
                "task": r["task"],
                "payload": _json_loads_maybe(r["payload"]) or {},
                "status": r["status"],
                "result": _json_loads_maybe(r["result"]),
                "attempts": r["attempts"] if "attempts" in keys else 0,
                "priority": r["priority"] if "priority" in keys else 0,
                "next_run_at": r["next_run_at"] if "next_run_at" in keys else None,
                "last_error": r["last_error"] if "last_error" in keys else None,
            }
        )
    return out
