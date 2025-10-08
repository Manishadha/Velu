from dataclasses import dataclass
from typing import Any, Protocol


class Agent(Protocol):
    def handle(self, task: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class TaskResult:
    status: str  # 'ok' | 'error'
    data: dict[str, Any]
    message: str = ""
