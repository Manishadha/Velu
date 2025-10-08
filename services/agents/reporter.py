from __future__ import annotations

from typing import Any


def handle(task: str, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Simple reporter: formats a tiny report string.
    """
    title = str(payload.get("title") or "Report")
    data = payload.get("data")
    snippet = str(data)[:160] if data is not None else "<no data>"
    return {
        "agent": "reporter",
        "task": task,
        "payload": payload,
        "result": {
            "title": title,
            "text": f"{title}: {snippet}",
        },
        "ok": True,
    }
