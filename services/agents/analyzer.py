from __future__ import annotations

from typing import Any


def handle(task: str, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Toy analyzer: counts keys/values and echoes back.
    """
    keys = list((payload or {}).keys())
    return {
        "agent": "analyzer",
        "task": task,
        "payload": payload,
        "result": {
            "key_count": len(keys),
            "keys": keys,
            "summary": "analysis complete",
        },
        "ok": True,
    }
