import json, os, time
from typing import Dict, Any

USE_SQLITE = lambda: os.environ.get("TASK_BACKEND", "jsonl").lower() == "sqlite"

# -------- JSONL backend (current default) --------
def _log_path() -> str:
    return os.environ.get("TASK_LOG", "data/pointers/tasks.log")

def _append_jsonl(task: Dict[str, Any]) -> None:
    log = _log_path()
    os.makedirs(os.path.dirname(log), exist_ok=True)
    rec = {"ts": time.time(), **task}
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

def _list_jsonl(limit: int = 50):
    path = _log_path()
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return list(reversed(out[-limit:]))

# -------- public API (delegates to chosen backend) --------
def append_task(task: Dict[str, Any]) -> None:
    if USE_SQLITE():
        from services.app_server import store_sqlite as s
        s.init_db()
        s.insert(task)
    else:
        _append_jsonl(task)

def recent_tasks(limit: int = 50):
    if USE_SQLITE():
        from services.app_server import store_sqlite as s
        s.init_db()
        return s.list_recent(limit=limit)
    else:
        return _list_jsonl(limit=limit)
