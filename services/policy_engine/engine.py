from __future__ import annotations

from typing import Any


def evaluate(task: dict[str, Any]) -> dict[str, Any]:
    """
    Return a normalized decision:
      {"allowed": bool, "rules_triggered": [..], "notes": str}

    Stub rule:
      - deny when task == "deploy"
      - allow otherwise
    """
    name = (task or {}).get("task", "")
    if name == "deploy":
        return {
            "allowed": False,
            "rules_triggered": ["deny_deploy_stub"],
            "notes": "Denied by default stub rule",
        }
    return {"allowed": True, "rules_triggered": [], "notes": "Allowed by default"}
