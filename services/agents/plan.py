"""Simple planning agent."""

from __future__ import annotations


def run(payload: dict | None = None) -> dict:
    """Return a tiny plan based on the input payload."""
    payload = payload or {}
    idea = payload.get("idea")
    steps = ["collect inputs", "draft plan", "review", "finalize"]

    return {
        "ok": True,
        "agent": "planner",
        "task": "plan",
        "steps": steps,
        "inputs": {"idea": idea} if idea is not None else {},
    }
