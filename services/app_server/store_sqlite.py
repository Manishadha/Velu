import os, time, sqlite3
from typing import Iterable, Dict, Any

DB_PATH = lambda: os.environ.get("TASK_DB", "data/pointers/tasks.db")

def _conn():
    os.makedirs(os.path.dirname(DB_PATH()), exist_ok=True)
    return sqlite3.connect(DB_PATH())

def init_db():
    with _conn() as cx:
        cx.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            task TEXT NOT NULL,
            payload TEXT NOT NULL
        );
        """)
        cx.commit()

def insert(task: Dict[str, Any]) -> None:
    import json
    with _conn() as cx:
        cx.execute(
            "INSERT INTO tasks (ts, task, payload) VALUES (?, ?, ?)",
            (time.time(), task["task"], json.dumps(task["payload"], ensure_ascii=False)),
        )
        cx.commit()

def list_recent(limit: int = 50) -> Iterable[Dict[str, Any]]:
    import json
    with _conn() as cx:
        rows = cx.execute(
            "SELECT id, ts, task, payload FROM tasks ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    out = []
    for rid, ts, task, payload in rows:
        out.append({"id": rid, "ts": ts, "task": task, "payload": json.loads(payload)})
    return out
