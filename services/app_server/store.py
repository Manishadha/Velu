# services/app_server/store.py
from __future__ import annotations

import json
import os
import sqlite3
import time
from collections import deque
from collections.abc import Iterable
from typing import Any

# --- path helpers ------------------------------------------------------------


def _db_path() -> str:
    """
    Decide where the SQLite DB should live.

    Priority:
      1) TASK_DB if explicitly provided
      2) If TASK_LOG is set, co-locate DB next to it (pytest tmp dir -> writable)
      3) Fallback to data/ (may be read-only in some envs, but fine for local)
    """
    db_env = os.getenv("TASK_DB")
    if db_env:
        return db_env

    log_env = os.getenv("TASK_LOG")
    if log_env:
        base = os.path.dirname(log_env) or "."
        return os.path.join(base, "jobs.db")

    return os.path.join("data", "jobs.db")


def _base_dir() -> str:
    return os.path.dirname(_db_path()) or "."


def _resolve_paths() -> tuple[str, str]:
    """
    Choose paths that are writable in tests:
    - If TASK_LOG is set, write tasks.jsonl alongside it.
    - Otherwise, use the DB directory (defaults to data/).
    """
    db_base = _base_dir()
    log_path_env = os.getenv("TASK_LOG")
    log_path = log_path_env or os.path.join(db_base, "tasks.log")
    jsonl_dir = os.path.dirname(log_path) if log_path_env else db_base
    jsonl_path = os.path.join(jsonl_dir, "tasks.jsonl")
    return log_path, jsonl_path


# --- file logging (human + jsonl) -------------------------------------------


def _append_jsonl(task: dict[str, Any]) -> None:
    _, jsonl_path = _resolve_paths()
    os.makedirs(os.path.dirname(jsonl_path) or ".", exist_ok=True)
    record = dict(task)
    record.setdefault("ts", time.time())
    with open(jsonl_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# --- sqlite compatibility insert --------------------------------------------


def _insert_db_row(task: dict[str, Any]) -> None:
    """
    tests/unit/test_store_ts_compat.py expects INSERT into tasks table.
    - If 'ts' col exists and is NOT NULL, we must supply it.
    - If 'ts' col doesn't exist, insert without it.

    We never create the table here; we insert only if it already exists.
    """
    db_path = _db_path()
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    payload_json = json.dumps(task.get("payload", {}))

    # Use context manager so we always commit properly
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        cols = {r["name"] for r in con.execute("PRAGMA table_info(tasks)")}
        if not cols:
            # Table doesn't exist in this DB; silently skip (matches test expectations)
            return

        if "ts" in cols:
            ts_val = int(time.time())
            con.execute(
                "INSERT INTO tasks(task, payload, ts) VALUES(?,?,?)",
                (task.get("task", ""), payload_json, ts_val),
            )
        else:
            con.execute(
                "INSERT INTO tasks(task, payload) VALUES(?,?)",
                (task.get("task", ""), payload_json),
            )
        # implicit commit on successful exit


def append_task(task: dict[str, Any]) -> None:
    log_path, _ = _resolve_paths()
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)

    # human-readable line log
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(task, ensure_ascii=False) + "\n")

    # structured jsonl
    _append_jsonl(task)

    # optional sqlite insert (only if tasks table already exists)
    _insert_db_row(task)


# --- reads -------------------------------------------------------------------


def _tail_lines(path: str, limit: int) -> Iterable[str]:
    if not os.path.exists(path):
        return []
    dq: deque[str] = deque(maxlen=max(1, limit))
    with open(path, encoding="utf-8") as f:
        for line in f:
            dq.append(line.rstrip("\n"))
    return list(dq)


def recent_tasks(limit: int = 100) -> list[dict[str, Any]]:
    _, jsonl_path = _resolve_paths()
    out: list[dict[str, Any]] = []
    for line in _tail_lines(jsonl_path, limit):
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    # newest-first for tests that expect latest insert at index 0
    out.reverse()
    return out
