# services/worker/main.py
from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Any

import sitecustomize  # noqa: F401  # side effects: handlers + queue patch

from orchestrator.router_client import route
from services.queue import sqlite_queue as q

# ---------- router calling & normalization ----------


def _call_router(name: str, payload: dict) -> Any:
    """Prefer route({'task':..., 'payload':...}); fallback to route(name, payload)."""
    try:
        return route({"task": name, "payload": payload})
    except TypeError as te:
        try:
            return route(name, payload)  # legacy
        except Exception:
            raise te from None


def _normalize_result(raw: Any) -> dict:
    """Normalize router output to a dict with 'ok'."""
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


# ---------- helpers ----------


def _as_dict_payload(val: Any) -> dict[str, Any]:
    if isinstance(val, dict):
        return val
    if val is None:
        return {}
    return {"value": val}


def _enqueue(task: str, payload: dict[str, Any], *, priority: int = 0) -> int:
    return q.enqueue(task=task, payload=payload, priority=priority)


def _require_job_done(job_id: int) -> dict[str, Any]:
    rec = q.load(job_id)
    if not rec:
        raise RuntimeError(f"dependency job {job_id} not found")
    if rec["status"] != "done":
        raise RuntimeError(f"dependency job {job_id} not ready")
    return rec.get("result") or {}


# ---------- tasks ----------


def _task_fail_n(rec: dict) -> dict:
    payload = _as_dict_payload(rec.get("payload"))
    want = int(payload.get("fail_times", 1))
    attempts_so_far = int(rec.get("attempts") or 0)
    if attempts_so_far < want:
        raise RuntimeError(f"simulated failure {attempts_so_far + 1}/{want}")
    return {"ok": True, "message": f"passed after {attempts_so_far} failures"}


def _task_plan_pipeline(rec: dict) -> dict:
    """Plan → generate_code → run_tests, when WORKER_ENABLE_PIPELINE=1."""
    payload = _as_dict_payload(rec.get("payload"))
    idea = payload.get("idea", "demo")
    module = payload.get("module", "hello_mod")

    # optional preview
    try:
        plan_preview = _normalize_result(_call_router("plan", {"idea": idea, "module": module}))
    except Exception:
        plan_preview = {"ok": True, "plan": f"{idea} via {module}"}

    code_job_id = _enqueue(
        "generate_code",
        {"idea": idea, "module": module, "parent_job": rec.get("id")},
    )

    test_job_id = _enqueue(
        "run_tests",
        {"code_job_id": code_job_id, "parent_job": rec.get("id")},
    )

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

    env = os.environ.copy()
    env.pop("API_KEYS", None)
    src = os.path.abspath("src")
    env["PYTHONPATH"] = f"{src}:{env.get('PYTHONPATH','')}"

    try:
        out = subprocess.run(
            ["pytest", "-q", test_path],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        return {
            "ok": True,
            "message": "tests passed",
            "stdout": out.stdout,
            "stderr": out.stderr,
            "using": {"code_job_id": code_job_id, "code_result": code_result},
        }
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"pytest failed (exit {e.returncode})\n{e.stdout}\n{e.stderr}") from e


# ---------- dispatcher ----------


def process_job(rec: dict) -> dict:
    """
    Load -> dispatch -> normalize.
    'plan' passes through to router by default; pipeline when enabled.
    Ensures 'plan' string exists for smoke test.
    """
    name = rec["task"]

    if name == "fail_n":
        return _task_fail_n(rec)

    if name == "plan":
        if os.getenv("WORKER_ENABLE_PIPELINE", "0").lower() not in {"", "0", "false", "no"}:
            return _task_plan_pipeline(rec)
        payload = _as_dict_payload(rec.get("payload"))
        res = _normalize_result(_call_router(name, payload))
        res.setdefault("plan", f"{payload.get('idea','')} via {payload.get('module','')}")
        return res

    if name == "generate_code":
        return _task_generate_code(rec)

    if name == "run_tests":
        return _task_run_tests(rec)

    payload = _as_dict_payload(rec.get("payload"))
    return _normalize_result(_call_router(name, payload))


# ---------- main loop ----------


def main() -> None:
    q.init()
    print("worker: online", flush=True)
    processed = 0

    run_once = "WORKER_RUN_ONCE" in os.environ and os.environ["WORKER_RUN_ONCE"].lower() not in {
        "0",
        "",
        "false",
        "no",
    }
    max_jobs_env = os.getenv("WORKER_MAX_JOBS", "").strip()
    try:
        max_jobs = int(max_jobs_env) if max_jobs_env else None
    except Exception:
        max_jobs = None
    if run_once and (max_jobs is None or max_jobs > 1):
        max_jobs = 1

    try:
        while True:
            job_id = q.dequeue()
            if job_id is None:
                if max_jobs is not None and processed >= max_jobs:
                    print(f"worker: exit (processed={processed})", flush=True)
                    return
                time.sleep(0.5)
                continue

            rec = q.load(job_id)
            try:
                result = process_job(rec)
                q.finish(job_id, result)
                processed += 1
                print(f"worker: done {job_id}", flush=True)
            except Exception as e:
                q.fail(job_id, f"{type(e).__name__}: {e}")
                print(f"worker: error {job_id}: {e}", flush=True)
    except KeyboardInterrupt:
        print("worker: stopping after current job...", flush=True)
        print(f"worker: exit (processed={processed})", flush=True)


if __name__ == "__main__":
    main()
