from __future__ import annotations

import importlib
import inspect
import json
import logging
import sys
import time
import threading
from contextlib import suppress
from typing import Any, Callable

# ------------------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------------------
log = logging.getLogger("sitecustomize")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

# ------------------------------------------------------------------------------
# Ensure overlay paths (/app, /app/src) are importable inside the container
# ------------------------------------------------------------------------------
for p in ("/app", "/app/src"):
    if p not in sys.path:
        sys.path.insert(0, p)


# ------------------------------------------------------------------------------
# Helper: adapt any handler to the worker's expected (name, payload) -> dict shape
# ------------------------------------------------------------------------------
def _adapt_handler(fn: Callable[..., Any]) -> Callable[[str, dict[str, Any]], dict[str, Any]]:
    """
    Accept a handler that may be either:
      - fn(payload) -> dict | Any
      - fn(name, payload) -> dict | Any
    and adapt it to the worker's (name, payload) -> dict form.
    """
    with suppress(Exception):
        params = list(inspect.signature(fn).parameters.values())
        if len(params) == 1:  # payload-only

            def _wrapped(name: str, payload: dict[str, Any]) -> dict[str, Any]:
                out = fn(payload)
                return out if isinstance(out, dict) else {"ok": True, "data": out}

            return _wrapped

    # Already (name, payload) form (or something compatible)
    def _wrapped(name: str, payload: dict[str, Any]) -> dict[str, Any]:
        out = fn(name, payload)
        return out if isinstance(out, dict) else {"ok": True, "data": out}

    return _wrapped


# ------------------------------------------------------------------------------
# Step 1: Register local tasks into services.agents.HANDLERS
# ------------------------------------------------------------------------------
def _install_local_handlers() -> None:
    try:
        # Prefer "local_tasks" from the overlay (mounted as /app/src/local_tasks.py)
        lt = importlib.import_module("local_tasks")
    except Exception as e:
        log.info("local_tasks import failed: %r", e)
        return

    try:
        agents = importlib.import_module("services.agents")
        handlers = getattr(agents, "HANDLERS", None)
        if not isinstance(handlers, dict):
            raise RuntimeError("services.agents.HANDLERS is not a dict")

        def _register(name: str, fn: Callable[..., Any]) -> None:
            handlers[name] = _adapt_handler(fn)

        # Preferred hook: local_tasks.register(cb)
        reg = getattr(lt, "register", None)
        if callable(reg):
            with suppress(TypeError):
                reg(_register)

        # Fallback: common names
        for name in ("plan", "generate_code", "codegen"):
            fn = getattr(lt, name, None)
            if callable(fn) and name not in handlers:
                handlers[name] = _adapt_handler(fn)

        log.info("HANDLERS active: %s", sorted(handlers.keys()))
    except Exception as e:
        log.info("local_tasks registration failed: %r", e)


# ------------------------------------------------------------------------------
# Step 2: DB patching shims
# ------------------------------------------------------------------------------
def _db_pop_one_fixed_factory(_connect):
    """Return a _db_pop_one that reads payload JSON and key from jobs."""

    def _db_pop_one_fixed() -> dict[str, Any] | None:
        con = _connect()
        con.row_factory = getattr(__import__("sqlite3"), "Row")
        cur = con.cursor()
        try:
            cur.execute("BEGIN IMMEDIATE")
            cur.execute(
                """
                SELECT id, task, payload, key
                  FROM jobs
                 WHERE status='queued'
                 ORDER BY id ASC
                 LIMIT 1
                """
            )
            row = cur.fetchone()
            if not row:
                con.commit()
                return None

            jid = int(row["id"])
            cur.execute("UPDATE jobs SET status='working' WHERE id=?", (jid,))
            con.commit()

            # Normalize task name
            task_name: Any = row["task"]
            if isinstance(task_name, (bytes, bytearray)):
                task_name = task_name.decode("utf-8", errors="ignore")
            if not isinstance(task_name, str):
                task_name = str(task_name or "")
            task_name = task_name.strip() or "unknown"

            # Normalize payload (JSON stored in 'payload' column)
            raw_payload: Any = row["payload"]
            if isinstance(raw_payload, (bytes, bytearray)):
                raw_payload = raw_payload.decode("utf-8", errors="ignore")

            payload: dict[str, Any] = {}
            if isinstance(raw_payload, str):
                with suppress(Exception):
                    parsed = json.loads(raw_payload)
                    if isinstance(parsed, dict):
                        payload = parsed
                    else:
                        payload = {"raw": parsed}
            elif isinstance(raw_payload, dict):
                payload = raw_payload
            elif raw_payload is not None:
                payload = {"raw": raw_payload}

            task_obj = {"task": task_name, "payload": payload}
            return {"id": jid, "task": task_obj, "key": row["key"]}
        finally:
            with suppress(Exception):
                con.close()

    return _db_pop_one_fixed


def _db_set_result_fixed(
    con, job_id: int, ok: bool, result: dict | None, error: str | None, status: str = "done"
) -> None:
    """Write results into `result` JSON and `last_error` (compat for legacy 'err')."""
    payload = json.dumps(result or {}, ensure_ascii=False)
    cur = con.cursor()
    cur.execute(
        "UPDATE jobs SET status=?, result=?, last_error=? WHERE id=?",
        (status, payload, error, job_id),
    )
    con.commit()


def _db_set_error_fixed(con, job_id: int, error: str | None) -> None:
    """Write error into last_error and set status='error'."""
    cur = con.cursor()
    cur.execute(
        "UPDATE jobs SET status=?, last_error=? WHERE id=?",
        ("error", error, job_id),
    )
    con.commit()


def _try_patch_worker() -> bool:
    """Try to patch services.queue.worker_entry; return True if patched."""
    try:
        we = importlib.import_module("services.queue.worker_entry")
    except Exception as e:
        log.info("sitecustomize: worker_entry not ready yet: %r", e)
        return False

    _connect = getattr(we, "_connect", None)
    if not callable(_connect):
        log.info("sitecustomize: worker_entry._connect not available yet")
        return False

    # Patch pop
    we._db_pop_one = _db_pop_one_fixed_factory(_connect)
    # Patch set_result / set_error
    we._db_set_result = _db_set_result_fixed
    we._db_set_error = _db_set_error_fixed

    log.info("sitecustomize: patched worker_entry DB functions.")
    return True


def _ensure_patch_with_retry() -> None:
    if _try_patch_worker():
        return

    def _retry():
        for _ in range(50):  # ~5s
            if _try_patch_worker():
                return
            time.sleep(0.1)
        log.warning("sitecustomize: gave up patching worker_entry")

    threading.Thread(target=_retry, name="sitecustomize-patch", daemon=True).start()


# ------------------------------------------------------------------------------
# Import-time side effects
# ------------------------------------------------------------------------------
with suppress(Exception):
    _install_local_handlers()
with suppress(Exception):
    _ensure_patch_with_retry()
