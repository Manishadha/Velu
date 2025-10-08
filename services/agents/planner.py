# services/agents/planner.py
from __future__ import annotations

from typing import Any


def handle(task_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Minimal 'plan' agent: echoes a simple plan based on the payload.
    """
    steps: list[str] = []

    if payload.get("demo"):
        steps = [
            "analyze requirements",
            "propose approach",
            "execute minimal POC",
            "report metrics",
        ]
    else:
        steps = ["collect inputs", "draft plan", "review", "finalize"]

    return {
        "agent": "planner",
        "task": task_name,
        "steps": steps,
        "inputs": payload,
    }
