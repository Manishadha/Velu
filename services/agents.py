# services/agents.py
from __future__ import annotations

import importlib
import os
import sys
from collections.abc import Callable
from typing import Any

Handler = Callable[[str, dict[str, Any]], dict[str, Any]]
HANDLERS: dict[str, Handler] = {}


def register(name: str, fn: Handler) -> None:
    """Register a task handler. Signature: fn(name, payload) -> dict."""
    key = (name or "").strip().lower()
    if not key:
        raise ValueError("handler name cannot be empty")
    HANDLERS[key] = fn


def _unknown(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"ok": False, "error": f"unknown task: {name}", "data": payload}


register("unknown", _unknown)


LOCAL_TASKS_MODULE = os.environ.get("LOCAL_TASKS_MODULE", "local_tasks")
DEFAULT_LOCAL_PATH = os.path.join(os.getcwd(), "data", "src")
LOCAL_TASKS_PATH = os.environ.get("LOCAL_TASKS_PATH", DEFAULT_LOCAL_PATH)


def _ensure_local_tasks_on_path() -> None:
    """
    Make sure a plausible path (e.g., ./data/src) is importable so that
    `import local_tasks` works in pytest/CI outside Docker.
    """

    candidates = []
    if LOCAL_TASKS_PATH:
        candidates.append(LOCAL_TASKS_PATH)

    if DEFAULT_LOCAL_PATH not in candidates:
        candidates.append(DEFAULT_LOCAL_PATH)

    for p in candidates:
        if p and os.path.isdir(p) and p not in sys.path:
            sys.path.append(p)


def _wrap_payload_only(fn: Callable[[dict[str, Any]], dict[str, Any]]) -> Handler:
    def _w(name: str, payload: dict[str, Any]) -> dict[str, Any]:
        out = fn(payload or {})
        return out if isinstance(out, dict) else {"ok": True, "data": out}

    return _w


def _try_load_local() -> None:
    _ensure_local_tasks_on_path()
    try:
        lt = importlib.import_module(LOCAL_TASKS_MODULE)
    except Exception:
        return

    reg = getattr(lt, "register", None)
    if callable(reg):
        reg(register)
        return

    plan_handler = getattr(lt, "plan_handler", None)
    if callable(plan_handler) and "plan" not in HANDLERS:
        register("plan", _wrap_payload_only(plan_handler))


_try_load_local()
