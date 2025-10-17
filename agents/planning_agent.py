from orchestrator.agent_contracts import TaskResult


def handle(task: dict) -> dict:
    return TaskResult(status="ok", data={"agent": "planning", "received": task}).__dict__
