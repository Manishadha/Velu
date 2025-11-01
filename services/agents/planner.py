from __future__ import annotations

from typing import Any

from services.queue import sqlite_queue as q


def handle(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Simple planner."""
    idea = str(payload.get("idea", "demo"))
    module = str(payload.get("module", "hello_mod"))
    return {"ok": True, "plan": f"{idea} via {module}"}


def handle_pipeline(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Orchestrator task:
      - enqueues 'plan'
      - enqueues 'codegen' (built-in generator)
    Returns subjob IDs so /results/{id}?expand=1 can show details.
    On failure, returns ok=False with error details (no exception escapes).
    """
    idea = str(payload.get("idea", "demo"))
    module = str(payload.get("module", "hello_mod"))

    try:
        plan_id = q.enqueue(
            task="plan",
            payload={"idea": idea, "module": module},
            priority=0,
        )
    except Exception as e:
        return {
            "ok": False,
            "stage": "enqueue-plan",
            "error": str(e),
            "inputs": {"idea": idea, "module": module},
        }

    try:
        gen_id = q.enqueue(
            task="codegen",  # IMPORTANT: use the built-in codegen agent
            payload={"idea": idea, "module": module},
            priority=0,
        )
    except Exception as e:
        return {
            "ok": False,
            "stage": "enqueue-codegen",
            "error": str(e),
            "subjobs": {"plan": plan_id},
            "inputs": {"idea": idea, "module": module},
        }

    return {
        "ok": True,
        "msg": "pipeline started",
        "subjobs": {
            "plan": plan_id,
            "generate": gen_id,
        },
    }
