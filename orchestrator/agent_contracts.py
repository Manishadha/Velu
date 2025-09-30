from dataclasses import dataclass
from typing import Any, Dict, Protocol

class Agent(Protocol):
    def handle(self, task: Dict[str, Any]) -> Dict[str, Any]: ...

@dataclass
class TaskResult:
    status: str  # 'ok' | 'error'
    data: Dict[str, Any]
    message: str = ''
