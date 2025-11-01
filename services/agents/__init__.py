from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import analyzer, codegen, executor, planner, reporter
from .planner import handle_pipeline  # keep import at top (ruff E402)

Handler = Callable[[str, dict[str, Any]], dict[str, Any]]
HANDLERS: dict[str, Handler] = {}


def register(name: str, fn: Handler) -> None:
    key = (name or "").strip().lower()
    if not key:
        raise ValueError("handler name cannot be empty")
    HANDLERS[key] = fn


# Built-ins
register("plan", planner.handle)
register("codegen", codegen.handle)
register("execute", executor.handle)
register("analyze", analyzer.handle)
register("report", reporter.handle)

# Orchestrator
register("pipeline", handle_pipeline)
