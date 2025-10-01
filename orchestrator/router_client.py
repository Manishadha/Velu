
from typing import Any, Dict

import httpx

from orchestrator.state_manager import record

API_URL = "http://api:8000"  # docker-compose service DNS


def route(task: Dict[str, Any]) -> Dict[str, Any]:
    # 1) health check
    try:
        httpx.get(f"{API_URL}/health", timeout=3.0).raise_for_status()
    except Exception as e:
        err = {"status": "error", "message": f"api health check failed: {e!s}"}
        record({"type": "api_health_error", **err})
        return err

    # 2) if it's a planning task, POST to API /tasks
    if task.get("task") == "plan":
        try:
            r = httpx.post(f"{API_URL}/tasks", json=task, timeout=5.0)
            r.raise_for_status()
            reply = r.json()
            out = {"status": "ok", "api_reply": reply}
            record({"type": "task_posted", "request": task, "response": reply})
            return out
        except Exception as e:
            err = {"status": "error", "message": f"task post failed: {e!s}"}
            record({"type": "task_post_error", "request": task, **err})
            return err

    # 3) default echo
    res = {"status": "ok", "echo": task}
    record({"type": "echo", "payload": task})
    return res
