from __future__ import annotations

import importlib
import io
import json
import os
import sys
import threading
import time
from contextlib import redirect_stderr, redirect_stdout
from typing import Any

import pytest

from orchestrator.router_client import route


def _truthy(v: str | None) -> bool:
    return bool(v) and v.lower() not in {"0", "", "false", "no"}


def _q():
    return importlib.import_module("services.queue.sqlite_queue")


# optional embedded worker (useful for smoke tests started via API)
def _start_embedded_worker() -> None:
    if getattr(_start_embedded_worker, "_started", False):
        return
    _start_embedded_worker._started = True

    def _run():
        try:
            from services.worker.main import main as _main

            _main()
        except Exception as e:
            print(f"[embedded-worker] fatal: {e}", file=sys.stderr, flush=True)

    t = threading.Thread(target=_run, name="embedded-worker", daemon=True)
    t.start()


if _truthy(os.getenv("EMBEDDED_WORKER", "1")):
    _start_embedded_worker()


def _call_router(name: str, payload: dict) -> Any:
    try:
        return route({"task": name, "payload": payload})
    except TypeError as te:
        try:
            return route(name, payload)
        except Exception:
            # preserve original TypeError per tests
            raise te from None


def _normalize_result(raw: Any) -> dict:
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
            return {"ok": True, "data": parsed}
        except Exception:
            return {"ok": True, "data": raw}
    if isinstance(raw, dict):
        return raw
    return {"ok": True, "data": raw}


def _as_dict_payload(val: Any) -> dict[str, Any]:
    if isinstance(val, dict):
        return val
    if val is None:
        return {}
    return {"value": val}


def _enqueue(task: str, payload: dict[str, Any], *, priority: int = 0) -> int:
    return _q().enqueue(task=task, payload=payload, priority=priority)


def _require_job_done(job_id: int) -> dict[str, Any]:
    rec = _q().load(job_id)
    if not rec:
        raise RuntimeError(f"dependency job {job_id} not found")
    if rec["status"] != "done":
        raise RuntimeError(f"dependency job {job_id} not ready")
    return rec.get("result") or {}


def _task_fail_n(rec: dict) -> dict:
    payload = _as_dict_payload(rec.get("payload"))
    want = int(payload.get("fail_times", 1))
    attempts_so_far = int(rec.get("attempts") or 0)
    if attempts_so_far < want:
        raise RuntimeError(f"simulated failure {attempts_so_far + 1}/{want}")
    return {"ok": True, "message": f"passed after {attempts_so_far} failures"}


def _task_plan_pipeline(rec: dict) -> dict:
    payload = _as_dict_payload(rec.get("payload"))
    idea = payload.get("idea", "demo")
    module = payload.get("module", "hello_mod")
    try:
        plan_preview = _normalize_result(_call_router("plan", {"idea": idea, "module": module}))
    except Exception:
        plan_preview = {"ok": True, "plan": f"{idea} via {module}"}

    code_job_id = _enqueue(
        "generate_code", {"idea": idea, "module": module, "parent_job": rec.get("id")}
    )
    test_job_id = _enqueue("run_tests", {"code_job_id": code_job_id, "parent_job": rec.get("id")})

    return {
        "ok": True,
        "message": "pipeline created",
        "subjobs": {"generate_code": code_job_id, "run_tests": test_job_id},
        "plan": plan_preview.get("plan", f"{idea} via {module}"),
    }


def _task_generate_code(rec: dict) -> dict:
    payload = _as_dict_payload(rec.get("payload"))
    idea = payload.get("idea", "demo")
    module = payload.get("module", "hello_mod")

    os.makedirs("src", exist_ok=True)
    os.makedirs("tests", exist_ok=True)

    mod_path = f"src/{module}.py"
    test_path = f"tests/test_{module}.py"

    with open(mod_path, "w", encoding="utf-8") as f:
        f.write("def greet(name: str) -> str:\n" '    return f"Hello, {name}!"\n')

    with open(test_path, "w", encoding="utf-8") as f:
        f.write(
            f"from {module} import greet\n\n"
            "def test_greet():\n"
            "    assert greet('Velu') == 'Hello, Velu!'\n"
        )

    return {
        "ok": True,
        "message": "code generated",
        "idea": idea,
        "module": module,
        "files": [mod_path, test_path],
    }


def _task_run_tests(rec: dict) -> dict:
    payload = _as_dict_payload(rec.get("payload"))
    code_job_id = int(payload.get("code_job_id", 0))
    if not code_job_id:
        raise RuntimeError("missing code_job_id")

    code_result = _require_job_done(code_job_id)
    module = (code_result or {}).get("module", "hello_mod")
    test_path = f"tests/test_{module}.py"

    src = os.path.abspath("src")
    if src not in sys.path:
        sys.path.insert(0, src)

    buf_out = io.StringIO()
    buf_err = io.StringIO()
    with redirect_stdout(buf_out), redirect_stderr(buf_err):
        rc = pytest.main(["-q", test_path])
    if rc != 0:
        raise RuntimeError(
            f"pytest returned exit code {rc}\n{buf_out.getvalue()}\n{buf_err.getvalue()}"
        )

    return {"ok": True, "stdout": buf_out.getvalue(), "stderr": buf_err.getvalue()}


def process_job(rec: dict) -> dict:
    name = rec["task"]

    if name == "fail_n":
        return _task_fail_n(rec)

    if name == "plan":
        payload = _as_dict_payload(rec.get("payload"))
        # Pipeline only when explicitly requested AND a module is provided.
        if _truthy(os.getenv("WORKER_ENABLE_PIPELINE")) and str(payload.get("module", "")).strip():
            return _task_plan_pipeline(rec)
        res = _normalize_result(_call_router(name, payload))
        module = str(payload.get("module", "")).strip()
        if module:
            idea = str(payload.get("idea", "")).strip()
            res.setdefault("plan", f"{idea} via {module}")
        return res

    if name == "generate_code":
        return _task_generate_code(rec)

    if name == "run_tests":
        return _task_run_tests(rec)

    payload = _as_dict_payload(rec.get("payload"))
    return _normalize_result(_call_router(name, payload))


def main() -> None:
    _q().init()
    print("worker: online", flush=True)
    processed = 0

    run_once = _truthy(os.getenv("WORKER_RUN_ONCE"))
    max_jobs_env = os.getenv("WORKER_MAX_JOBS", "").strip()
    try:
        max_jobs = int(max_jobs_env) if max_jobs_env else None
    except Exception:
        max_jobs = None
    if run_once and (max_jobs is None or max_jobs > 1):
        max_jobs = 1

    try:
        while True:
            job_id = _q().dequeue()
            if job_id is None:
                if max_jobs is not None and processed >= max_jobs:
                    print(f"worker: exit (processed={processed})", flush=True)
                    return
                time.sleep(0.5)
                continue

            rec = _q().load(job_id)
            try:
                result = process_job(rec)
                _q().finish(job_id, result)
                processed += 1
                print(f"worker: done {job_id}", flush=True)
            except Exception as e:
                _q().fail(job_id, f"{type(e).__name__}: {e}")
                print(f"worker: error {job_id}: {e}", flush=True)
    except KeyboardInterrupt:
        print("worker: stopping after current job...", flush=True)
        print(f"worker: exit (processed={processed})", flush=True)


if __name__ == "__main__":
    main()
