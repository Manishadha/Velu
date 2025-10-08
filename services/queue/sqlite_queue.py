import os
import sqlite3
import time
from typing import Any

DB = os.environ.get("TASK_DB", "data/pointers/tasks.db")

DDL = """
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  status TEXT NOT NULL,           -- queued | working | done | error
  task JSON NOT NULL,             -- original task payload
  result JSON,                    -- agent result
  err TEXT,                       -- error string if any
  key TEXT                        -- optional: api key bucket or owner
);
CREATE INDEX IF NOT EXISTS idx_jobs_status_ts ON jobs(status, ts);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
"""


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    conn = sqlite3.connect(DB, isolation_level=None)
    # Performance & reliability pragmas
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def init() -> None:
    with _conn() as c:
        for stmt in filter(None, (s.strip() for s in DDL.strip().split(";"))):
            c.execute(stmt)


def enqueue(task: dict[str, Any], key: str | None = None) -> int:
    import json

    init()
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO jobs(ts,status,task,key) VALUES(?,?,?,?)",
            (time.time(), "queued", json.dumps(task, ensure_ascii=False), key),
        )
        return cur.lastrowid


def dequeue() -> int | None:
    """
    Atomically claim the oldest queued job and mark as 'working'.
    Returns job_id or None if queue is empty.
    """
    init()
    with _conn() as c:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute(
            "SELECT id FROM jobs WHERE status='queued' ORDER BY ts ASC LIMIT 1"
        ).fetchone()
        if not row:
            c.execute("COMMIT")
            return None
        job_id = int(row[0])
        c.execute("UPDATE jobs SET status='working' WHERE id=?", (job_id,))
        c.execute("COMMIT")
        return job_id


def load(job_id: int) -> dict[str, Any]:
    import json

    with _conn() as c:
        row = c.execute(
            "SELECT id, ts, status, task, result, err, key FROM jobs WHERE id=?",
            (job_id,),
        ).fetchone()
        if not row:
            return {}
        task = json.loads(row[3]) if row[3] else None
        result = json.loads(row[4]) if row[4] else None
        return {
            "id": row[0],
            "ts": row[1],
            "status": row[2],
            "task": task,
            "result": result,
            "err": row[5],
            "key": row[6],
        }


def finish(job_id: int, result: dict[str, Any]) -> None:
    import json

    with _conn() as c:
        c.execute(
            "UPDATE jobs SET status='done', result=? WHERE id=?",
            (json.dumps(result, ensure_ascii=False), job_id),
        )


def fail(job_id: int, err: str) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE jobs SET status='error', err=? WHERE id=?",
            (err, job_id),
        )
