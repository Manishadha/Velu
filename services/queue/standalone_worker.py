# services/queue/standalone_worker.py
import json
import os
import sqlite3
import time
from contextlib import closing

DB_PATH = os.environ.get("TASK_DB", "/data/jobs.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       REAL,
    status   TEXT,
    task     TEXT,     -- JSON string: {"task": "...", "payload": {...}}
    result   TEXT,     -- JSON string or NULL
    err      TEXT,     -- JSON string or NULL
    key      TEXT
);
"""


def ensure_schema():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(SCHEMA)
        conn.commit()


def claim_one_job(conn: sqlite3.Connection):
    """
    Atomically claim one queued job by flipping status -> running.
    Returns (id, task_json) or None if none found.
    """
    conn.isolation_level = None  # manual transactions
    conn.execute("BEGIN IMMEDIATE")
    cur = conn.execute(
        "SELECT id, task FROM jobs WHERE status='queued' ORDER BY id ASC LIMIT 1"
    )
    row = cur.fetchone()
    if not row:
        conn.execute("COMMIT")
        return None
    job_id, task_json = row
    # claim if still queued
    cur = conn.execute(
        "UPDATE jobs SET status='running' WHERE id=? AND status='queued'",
        (job_id,),
    )
    if cur.rowcount != 1:
        conn.execute("ROLLBACK")
        return None
    conn.execute("COMMIT")
    return job_id, task_json


def complete_job(
    conn: sqlite3.Connection, job_id: int, result: dict | None, err: dict | None = None
):
    conn.execute(
        "UPDATE jobs SET status=?, result=?, err=? WHERE id=?",
        (
            "done" if err is None else "error",
            json.dumps(result) if result is not None else None,
            json.dumps(err) if err is not None else None,
            job_id,
        ),
    )
    conn.commit()


def process_task(task_obj: dict) -> dict:
    """
    Very simple handler so results show up.
    Extend this to call your router, models, etc.
    """
    name = task_obj.get("task")
    payload = task_obj.get("payload") or {}
    if name == "plan":
        idea = payload.get("idea", "")
        return {
            "message": "planned",
            "steps": [f"Think about: {idea}", "Draft outline", "Refine"],
            "echo": payload,
        }
    # default echo
    return {"message": "ok", "echo": payload}


def main():
    ensure_schema()
    print(f"worker: connected to {DB_PATH}", flush=True)
    while True:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            claimed = claim_one_job(conn)
            if not claimed:
                time.sleep(0.5)
                continue

            job_id, task_json = claimed
            try:
                task_obj = (
                    json.loads(task_json) if isinstance(task_json, str) else task_json
                )
                result = process_task(task_obj)
                complete_job(conn, job_id, result, None)
                print(f"worker: done {job_id}", flush=True)
            except Exception as e:
                complete_job(conn, job_id, None, {"error": str(e)})
                print(f"worker: error {job_id}: {e}", flush=True)


if __name__ == "__main__":
    main()
