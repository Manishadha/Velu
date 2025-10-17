from __future__ import annotations

from typing import Any

from agents.git_agent.agent import GitIntegrationAgent


def handle_git_task(task: dict[str, Any]) -> dict[str, Any]:
    """
    Payload examples:
      {"action":"feature","scope":"router","summary":"add /ready sqlite liveness probe","body":""}
      {"action":"fix","scope":"worker","summary":"handle missing pytest gracefully","body":""}
      {"action":"chore","scope":"ci","summary":"cache pip + matrix","body":""}
      {"action":"release","version":"1.2.3"}
    """
    agent = GitIntegrationAgent()
    action = task.get("action")

    if action == "feature":
        branch = agent.feature_commit(task["scope"], task["summary"], task.get("body", ""))
        return {"ok": True, "branch": branch}

    if action == "fix":
        branch = agent.fix_commit(task["scope"], task["summary"], task.get("body", ""))
        return {"ok": True, "branch": branch}

    if action == "chore":
        branch = agent.chore_commit(task["scope"], task["summary"], task.get("body", ""))
        return {"ok": True, "branch": branch}

    if action == "release":
        version = agent.release(task["version"], task.get("summary", ""))
        return {"ok": True, "version": version}

    return {"ok": False, "error": f"unknown action: {action}"}
