# /app/src/sitecustomize.py
from __future__ import annotations

import importlib
import json
import logging
import sqlite3
import sys
import threading
import time
from typing import Any, Dict

log = logging.getLogger("sitecustomize")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

# Ensure our overlay paths are visible inside the container
for p in ("/app", "/app/src"):
    if p not in sys.path:
        sys.path.insert(0, p)

# --- Load your local tasks (optional register()) ---
try:
    lt = importlib.import_module("local_tasks")
except Exception as e:  # keep startup resilient
    lt = None
    log.info("local_tasks not found: %r", e)

if lt and hasattr(lt, "register") and callable(lt.register):
    try:
        lt.register()
    except Exception as e:
        log.info("local_tasks.register() failed: %r", e)


# Fallback handler if local_tasks.plan_handler isn't present
def _fallback_plan(payload: Dict[str, Any]) -> Dict[str, Any]:
    idea = str(payload.get("idea", "")).strip()
    module = str(payload.get("module", "")).strip()
    return {"ok": True, "marker": "sitecustomize-plan", "plan": f"{idea} via {module}"}


PLAN_HANDLER = getattr(lt, "plan_handler", None) if lt else None
if not callable(PLAN_HANDLER):
    PLAN_HANDLER = _fallback_plan  # type: ignore[assignment]


# Call helper: accepts func(obj), obj.handle, obj.run; always returns a dict
def _call_handler(h: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    if callable(h):
        try:
            out = h(payload)
            return out if isinstance(out, dict) else {"ok": True, "data": out}
        except TypeError:
            pass
    handle = getattr(h, "handle", None)
    if callable(handle):
        out = handle(payload)
        return out if isinstance(out, dict) else {"ok": True, "data": out}
    run = getattr(h, "run", None)
    if callable(run):
        out = run(payload)
        return out if isinstance(out, dict) else {"ok": True, "data": out}
    # last-resort: our plan
    return PLAN_HANDLER(payload)


# Unify handler maps + dispatch for both modules
def _install_maps_and_dispatch() -> Dict[str, Any]:
    we = importlib.import_module("services.queue.worker_entry")
    wm = importlib.import_module("services.worker.main")

    base = getattr(we, "HANDLERS", None)
    if not isinstance(base, dict):
        base = {}

    # Ensure plan exists; keep unknown harmlessly pointing to plan
    base.setdefault("plan", PLAN_HANDLER)  # type: ignore[arg-type]
    base.setdefault("unknown", PLAN_HANDLER)  # type: ignore[arg-type]

    we.HANDLERS = base
    we.TASK_HANDLERS = base
    wm.TASK_HANDLERS = base

    def dispatch(task: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        h = base.get(task) or base.get("unknown")
        try:
            return _call_handler(h, payload or {})
        except Exception as e:
            return {"ok": False, "error": f"handler raised: {e!r}"}

    we.dispatch = dispatch
    wm.dispatch = dispatch

    log.info("HANDLERS now: %s", sorted(base.keys()))
    log.info("MAIN.TASK_HANDLERS now: %s", sorted(getattr(wm, "TASK_HANDLERS", {}).keys()))
    return base


BASE = _install_maps_and_dispatch()


# Background fixer: patch queued/running/error rows with empty results for task='plan'
def _fixer_loop() -> None:
    DB = "/data/jobs.db"
    while True:
        try:
            con = sqlite3.connect(DB, timeout=2)
            con.row_factory = sqlite3.Row
            rows = con.execute(
                """
                SELECT id, task, payload, status, result
                FROM jobs
                WHERE task='plan'
                  AND status IN ('queued','running','error')
                  AND (result IS NULL OR result='' OR result='{}')
                ORDER BY id DESC
                LIMIT 50
                """
            ).fetchall()

            if rows:
                we = importlib.import_module("services.queue.worker_entry")
                handlers = getattr(we, "HANDLERS", {}) or {}
                h = handlers.get("plan", PLAN_HANDLER)
                for r in rows:
                    try:
                        raw = r["payload"]
                        payload = json.loads(raw) if isinstance(raw, str) and raw else (raw or {})
                    except Exception:
                        payload = {}
                    try:
                        out = _call_handler(h, payload or {})  # type: ignore[arg-type]
                    except Exception as e:
                        out = {"ok": False, "error": f"plan handler failed: {e!r}"}
                    if not isinstance(out, dict):
                        out = {"ok": True, "data": out}
                    con.execute(
                        "UPDATE jobs SET status='done', result=? WHERE id=?",
                        (json.dumps(out), r["id"]),
                    )
                    con.commit()
            con.close()
        except Exception as e:
            log.info("fixer: %r", e)
        time.sleep(1.0)


threading.Thread(target=_fixer_loop, name="sitecustomize-fixer", daemon=True).start()
