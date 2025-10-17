# ./data/src/local_tasks.py

from __future__ import annotations
from typing import Any, Dict


def plan_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Simple example task: produces a tiny 'plan' summary."""
    idea = str(payload.get("idea", "")).strip()
    module = str(payload.get("module", "")).strip()
    return {"ok": True, "marker": "local-tasks-plan", "plan": f"{idea} via {module}"}


def register(register_fn) -> None:
    """
    Called by services.agents if present.
    Adapts our payload-only function to the worker's (name, payload) signature.
    """

    def _plan(name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return plan_handler(payload)

    register_fn("plan", _plan)
