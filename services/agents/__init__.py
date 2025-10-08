from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import analyzer, executor, planner, reporter

Handler = Callable[[str, dict[str, Any]], dict[str, Any]]

HANDLERS: dict[str, Handler] = {
    "plan": planner.handle,
    "execute": executor.handle,
    "analyze": analyzer.handle,
    "report": reporter.handle,
}
