# orchestrator/router_client.py
from __future__ import annotations

from typing import Any

from agents import planning_agent
from services.policy_engine.engine import evaluate as evaluate_policy


def route(task: dict[str, Any]) -> dict[str, Any]:
    """Very small router used by the worker to process tasks."""
    policy = evaluate_policy(task)

    # 3) simple task switch (expand as agents are added)
    kind = (task.get("task") or "").lower()
    out = planning_agent.handle(task) if kind == "plan" else {"ok": True, "echo": task}

    # minimal model description for downstream consumers (optional)
    model_name = getattr(getattr(planning_agent, "MODEL", None), "name", "mini-phi")
    return {
        "ok": True,
        "policy": policy,
        "model": {"name": model_name},
        "result": out,
    }
