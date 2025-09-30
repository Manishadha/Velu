from typing import Dict, Any
from agents import planning_agent

def route(task: Dict[str, Any]) -> Dict[str, Any]:
    if task.get("task") == "plan":
        return planning_agent.handle(task)
    return {"status": "ok", "echo": task}
