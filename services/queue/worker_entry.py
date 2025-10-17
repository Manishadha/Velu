from __future__ import annotations

import json
import os
import sqlite3
import time
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from services.agents import HANDLERS  # plan/analyze/execute/report handlers

DB_PATH = os.getenv("TASK_DB", "/data/jobs.db")


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    # Keep worker resilient under load
    con.execute("PRAGMA busy_timeout=5000;")
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    return con


def _db_pop_one() -> dict[str, Any] | None:
    """Atomically claim one queued job as 'working'. Returns dict or None."""
    con = _connect()
    cur = con.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        cur.execute(
            """
            SELECT id, task, key
              FROM jobs
             WHERE status='queued'
             ORDER BY id ASC
             LIMIT 1
            """
        )
        row = cur.fetchone()
        if not row:
            con.commit()
            return None

        jid = int(row["id"])
        cur.execute("UPDATE jobs SET status='working' WHERE id=?", (jid,))
        con.commit()

        task_obj: Any = row["task"]
        if isinstance(task_obj, bytes | bytearray):
            task_obj = task_obj.decode("utf-8", errors="ignore")
        if isinstance(task_obj, str):
            with suppress(Exception):
                task_obj = json.loads(task_obj)

        if not isinstance(task_obj, dict):
            task_obj = {"task": "unknown", "payload": {"raw": task_obj}}

        return {"id": jid, "task": task_obj, "key": row["key"]}
    finally:
        with suppress(Exception):
            con.close()


def _db_done(jid: int, result: dict[str, Any] | None, err: dict[str, Any] | None) -> None:
    con = _connect()
    cur = con.cursor()
    try:
        cur.execute(
            """
            UPDATE jobs
               SET status=?,
                   result=?,
                   err=?
             WHERE id=?
            """,
            (
                "done" if err is None else "error",
                json.dumps(result or {}, ensure_ascii=False),
                json.dumps(err, ensure_ascii=False) if err is not None else None,
                jid,
            ),
        )
        con.commit()
    finally:
        with suppress(Exception):
            con.close()


def _dispatch(task_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    name = (task_name or "").lower().strip()
    handler: Callable[[str, dict[str, Any]], dict[str, Any]] | None = HANDLERS.get(name)
    if handler is None:
        return {
            "ok": False,
            "agent": None,
            "error": f"unknown task: {name}",
            "data": {},
        }
    try:
        out = handler(name, payload)
        if not isinstance(out, dict):
            out = {"data": out}
        return {"ok": True, "agent": name, **out}
    except Exception as e:  # keep the worker robust
        return {"ok": False, "agent": name, "error": str(e), "data": {}}


def main() -> None:
    print(f"worker: connected to {DB_PATH}", flush=True)
    print("worker: mode=direct-db", flush=True)

    while True:
        try:
            item = _db_pop_one()
        except Exception as e:
            print("worker: pop failed:", e, flush=True)
            time.sleep(0.5)
            continue

        if not item:
            time.sleep(0.25)
            continue

        jid = int(item["id"])
        task_obj = item["task"]
        task_name = str(task_obj.get("task", ""))
        payload = task_obj.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {"raw": payload}

        result = _dispatch(task_name, payload)

        try:
            _db_done(
                jid,
                result=result if result.get("ok") else None,
                err=None if result.get("ok") else result,
            )
        except Exception as e:
            print(f"worker: done failed for {jid}: {e}", flush=True)
        else:
            print("worker: done", jid, f"task={task_name!r}", flush=True)


if __name__ == "__main__":
    main()
