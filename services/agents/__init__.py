# services/agents/__init__.py
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import analyzer, codegen, executor, planner, reporter

Handler = Callable[[str, dict[str, Any]], dict[str, Any]]

HANDLERS: dict[str, Handler] = {
    "plan": planner.handle,
    "execute": executor.handle,
    "analyze": analyzer.handle,
    "report": reporter.handle,
    "codegen": codegen.handle,
}


def get_handler(name: str) -> Handler:
    try:
        return HANDLERS[name]
    except KeyError as e:
        raise KeyError(f"unknown task: {name}") from e
