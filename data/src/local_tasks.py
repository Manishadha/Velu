from __future__ import annotations
from typing import Any, Dict, Callable
import inspect


# Your simple payload-only handler
def plan_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
    idea = str(payload.get("idea", "")).strip()
    module = str(payload.get("module", "")).strip()
    return {"ok": True, "marker": "local-tasks-plan", "plan": f"{idea} via {module}"}


def _wrap_if_needed(
    fn: Callable[..., Dict[str, Any]],
) -> Callable[[str, Dict[str, Any]], Dict[str, Any]]:
    """
    Ensure the function conforms to (name, payload) -> dict expected by the worker's agents map.
    If `fn` only accepts (payload), wrap it.
    """
    try:
        params = list(inspect.signature(fn).parameters.values())
    except Exception:
        # If we can't inspect, assume payload-only
        return lambda name, payload: fn(payload)

    if len(params) == 1:
        return lambda name, payload: fn(payload)
    return fn  


def register(
    register_fn: Callable[[str, Callable[[str, Dict[str, Any]], Dict[str, Any]]], None],
) -> None:
    """Called by sitecustomize with a `register_fn(name, handler)` callback."""
    register_fn("plan", _wrap_if_needed(plan_handler))
