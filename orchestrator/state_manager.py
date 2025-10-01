import json
import os
import time


def _log_path() -> str:
    return os.environ.get("ORCH_LOG", "data/pointers/orchestrator.log")


def record(event: dict) -> None:
    log = _log_path()
    os.makedirs(os.path.dirname(log), exist_ok=True)
    rec = {"ts": time.time(), **event}
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
