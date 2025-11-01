# services/agents.py
from __future__ import annotations

from collections.abc import Callable
from typing import Any

TaskFn = Callable[[dict[str, Any]], dict[str, Any]]


def _load_local_tasks():
    """
    Try multiple common paths so this works both locally and in Docker:
    - bind mount:    ./data/src -> /app/src        (your compose)
    - repo layout:   ./data/src                     (local runs / CI)
    - legacy path:   /app/data/src
    """
    import importlib
    import os
    import sys

    candidates = [
        "/app/src",
        os.path.join(os.getcwd(), "src"),
        "/app/data/src",
        os.path.join(os.getcwd(), "data", "src"),
    ]
    for p in candidates:
        if p and os.path.isdir(p) and p not in sys.path:
            sys.path.append(p)

    try:
        return importlib.import_module("local_tasks")
    except Exception:
        # last resort: stub module with only plan
        class _Stub:
            @staticmethod
            def plan(payload: dict) -> dict:
                idea = str(payload.get("idea", "demo"))
                module = str(payload.get("module", "hello_mod"))
                return {"ok": True, "plan": f"{idea} via {module}"}

        return _Stub()


local_tasks = _load_local_tasks()


def _missing_generate_code(_payload: dict[str, Any]) -> dict[str, Any]:
    return {"ok": False, "error": "generate_code not implemented in local_tasks.py"}


TASK_HANDLERS: dict[str, TaskFn] = {
    "plan": getattr(
        local_tasks,
        "plan",
        lambda p: {
            "ok": True,
            "plan": f"{p.get('idea','demo')} via {p.get('module','hello_mod')}",
        },
    ),
    "generate_code": getattr(local_tasks, "generate_code", _missing_generate_code),
}
