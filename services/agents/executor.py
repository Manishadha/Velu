from __future__ import annotations

from typing import Any


def handle(task: str, payload: dict[str, Any]) -> dict[str, Any]:
    """
    A safe 'executor' that *simulates* command execution.
    (No shelling-out here; this is intentional for safety.)
    """
    cmd = payload.get("cmd") or "echo 'no cmd provided'"
    return {
        "agent": "executor",
        "task": task,
        "payload": payload,
        "result": {"message": f"would run: {cmd}"},
        "ok": True,
    }
