# orchestrator/router_client.py
from __future__ import annotations

from typing import Any


def route(arg: Any, payload: dict | None = None) -> dict:
    # allow both: route("task", payload) and route({"task":..., "payload":...})
    if isinstance(arg, dict):
        name = str(arg.get("task", ""))
        pl = arg.get("payload") or {}
    else:
        name = str(arg or "")
        pl = payload or {}

    # --- simple pipeline ---
    if name == "plan":
        module = str(pl.get("module") or "hello_mod").replace("-", "_")
        path = f"generated/{module}.py"
        content = "def greet(name: str) -> str:\n" '    return f"Hello, {name}!"\n'
        return {
            "ok": True,
            "policy": {"allowed": True, "rules_triggered": [], "notes": "Allowed"},
            "model": {"name": "mini-phi"},
            "next": {"task": "codegen", "payload": {"path": path, "content": content}},
        }

    if name == "codegen":
        path = pl.get("path") or "generated/hello_mod.py"
        content = pl.get("content") or "print('hello')\n"
        return {"ok": True, "file": {"path": path, "content": content}}

    if name == "pytest":
        # worker will actually run pytest; this is just a placeholder
        return {"ok": True, "note": "pytest will be executed by worker"}

    # default fallback mirrors your earlier behavior
    return {
        "ok": True,
        "policy": {"allowed": True, "rules_triggered": [], "notes": "Allowed"},
        "model": {"name": "mini-phi"},
        "result": {
            "status": "ok",
            "data": {"agent": "planning", "received": {"task": name, "payload": pl}},
            "message": "",
        },
    }
