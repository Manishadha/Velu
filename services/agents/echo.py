from __future__ import annotations

from typing import Any


def handle(task: str, payload: dict[str, Any]) -> dict[str, Any]:
    # `task` is ignored here on purpose; this is an echo agent.
    return {"ok": True, "agent": "echo", "task": "echo", "data": payload or {}}
