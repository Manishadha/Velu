# services/agents.py
from __future__ import annotations

import importlib
import os
from collections.abc import Callable
from typing import Any

Handler = Callable[[str, dict[str, Any]], dict[str, Any]]
HANDLERS: dict[str, Handler] = {}


def register(name: str, fn: Handler) -> None:
    """Register a task handler. Signature: fn(name, payload) -> dict"""
    key = (name or "").strip().lower()
    if not key:
        raise ValueError("handler name cannot be empty")
    HANDLERS[key] = fn


# ---- built-ins --------------------------------------------------------------


def _unknown(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"ok": False, "error": f"unknown task: {name}", "data": payload}


register("unknown", _unknown)

# ---- optional local tasks (dev override) ------------------------------------
# If you bind-mount ./data/src -> /app/src, we can auto-load local tasks.
LOCAL_TASKS_MODULE = os.environ.get("LOCAL_TASKS_MODULE", "local_tasks")


def _wrap_payload_only(fn: Callable[[dict[str, Any]], dict[str, Any]]) -> Handler:
    def _w(name: str, payload: dict[str, Any]) -> dict[str, Any]:
        out = fn(payload or {})
        return out if isinstance(out, dict) else {"ok": True, "data": out}

    return _w


def _try_load_local() -> None:
    try:
        lt = importlib.import_module(LOCAL_TASKS_MODULE)
    except Exception:
        return

    # Preferred: local file exposes register(register_fn)
    reg = getattr(lt, "register", None)
    if callable(reg):
        reg(register)
        return

    # Back-compat: local file defines plan_handler(payload)
    plan_handler = getattr(lt, "plan_handler", None)
    if callable(plan_handler) and "plan" not in HANDLERS:
        register("plan", _wrap_payload_only(plan_handler))


_try_load_local()
