from __future__ import annotations

import sys
import logging
import importlib
import inspect
import json
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
    try:
        params = list(inspect.signature(fn).parameters.values())
        if len(params) == 1:  # payload-only
            def _wrapped(name: str, payload: dict[str, Any]) -> dict[str, Any]:
                out = fn(payload)
                return out if isinstance(out, dict) else {"ok": True, "data": out}
            return _wrapped
    except Exception:
        # If introspection fails, assume payload-only
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
        lt = importlib.import_module("local_tasks")
    except Exception as e:
        log.info("local_tasks import failed: %r", e)
        return

    try:
        agents = importlib.import_module("services.agents")
        handlers = getattr(agents, "HANDLERS", None)
        if not isinstance(handlers, dict):
            raise RuntimeError("services.agents.HANDLERS is not a dict")

        # Registration callback we pass to local_tasks.register()
        def _register(name: str, fn: Callable[..., Any]) -> None:
            handlers[name] = _adapt_handler(fn)

        if hasattr(lt, "register") and callable(getattr(lt, "register")):
            # Preferred: local_tasks.register(register_fn)
            try:
                lt.register(_register)
                log.info("local_tasks.register() succeeded; handlers now: %s", sorted(handlers.keys()))
            except TypeError as te:
                # In case local register() signature is different; log and fall back
                log.info("local_tasks.register() failed: %r", te)
        # Fallback: look for common handler names and register directly
        for name in ("plan",):
            fn = getattr(lt, f"{name}_handler", None)
            if callable(fn) and name not in handlers:
                handlers[name] = _adapt_handler(fn)
        log.info("HANDLERS active: %s", sorted(handlers.keys()))
    except Exception as e:
        log.info("local_tasks registration failed: %r", e)


# ------------------------------------------------------------------------------
# Step 2: Patch worker_entry._db_pop_one so it reads the 'payload' column
# ------------------------------------------------------------------------------
def _try_patch_pop() -> bool:
    """
    Try to import services.queue.worker_entry and patch _db_pop_one.
    Returns True if patched, False if worker_entry or _connect not ready yet.
    """
    try:
        we = importlib.import_module("services.queue.worker_entry")
    except Exception as e:
        log.info("sitecustomize: worker_entry not ready yet: %r", e)
        return False

    _connect = getattr(we, "_connect", None)
    if not callable(_connect):
        log.info("sitecustomize: worker_entry._connect not available yet")
        return False

    # Define the fixed version
    def _db_pop_one_fixed() -> dict[str, Any] | None:
        con = _connect()
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

    # Install the patch idempotently
    setattr(we, "_db_pop_one", _db_pop_one_fixed)
    log.info("sitecustomize: patched worker_entry._db_pop_one to read payload column.")
    return True


def _ensure_patch_with_retry() -> None:
    """Patch immediately; if not possible, retry a few times in the background."""
    if _try_patch_pop():
        return

    def _retry():
        for _ in range(50):  # ~5 seconds total
            if _try_patch_pop():
                return
            time.sleep(0.1)
        log.warning("sitecustomize: gave up patching worker_entry._db_pop_one")

    threading.Thread(target=_retry, name="sitecustomize-pop-patch", daemon=True).start()


# ------------------------------------------------------------------------------
# Import-time side effects
# ------------------------------------------------------------------------------
try:
    _install_local_handlers()
except Exception:
    log.exception("sitecustomize: _install_local_handlers failed")

try:
    _ensure_patch_with_retry()
except Exception:
    log.exception("sitecustomize: _ensure_patch_with_retry failed")
