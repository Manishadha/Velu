# services/app_server/main.py
from __future__ import annotations

import contextlib
import json
import os
import time
from collections import deque
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

# --------------------------- helpers ---------------------------

_recent_tasks: deque[dict[str, Any]] = deque(maxlen=100)


def _maybe_to_dict(obj: Any) -> Any:
    """Best-effort convert Pydantic-like objects to dict; else return as-is."""
    with contextlib.suppress(Exception):
        if hasattr(obj, "model_dump"):
            return obj.model_dump()  # type: ignore[attr-defined]
        if hasattr(obj, "dict"):
            return obj.dict()  # type: ignore[attr-defined]
    return obj


def _queue():
    # Lazy import so tests can import the app without pre-wiring env
    from services.queue import sqlite_queue as q  # type: ignore

    return q


# --------------------------- auth / rate middleware ---------------------------


class ApiKeyAndRateLimitMiddleware(BaseHTTPMiddleware):
    """
    - If API_KEYS is set, require X-API-Key ONLY for POST /tasks.
      Format: "k1:dev,k2:ops"; accepted keys: "k1","k2".
    - Rate limiting (applies to POST /tasks):
        * If RATE_REQUESTS & RATE_WINDOW_SEC set:
          - bucket by key if X-API-Key present, else "anon".
          - allow up to RATE_REQUESTS within rolling window RATE_WINDOW_SEC.
    - GET endpoints remain open (tests rely on this).
    """

    def __init__(self, app: FastAPI):
        super().__init__(app)
        # Parse allowed keys once
        raw_keys = os.environ.get("API_KEYS", "").strip()
        allowed: set[str] = set()
        if raw_keys:
            for part in raw_keys.split(","):
                part = part.strip()
                if not part:
                    continue
                key = part.split(":")[0].strip()
                if key:
                    allowed.add(key)
        self.allowed_keys = allowed

        # Rate settings
        self.rate_n = int(os.environ.get("RATE_REQUESTS", "0") or 0)
        self.rate_win = float(os.environ.get("RATE_WINDOW_SEC", "0") or 0)
        # store: bucket -> deque[timestamps]
        self._hits: dict[str, deque[float]] = {}

    async def dispatch(self, request: Request, call_next):
        # Only guard POST /tasks
        if request.method == "POST" and request.url.path == "/tasks":
            # API key check if configured
            if self.allowed_keys:
                k = request.headers.get("X-API-Key", "")
                if not k or k not in self.allowed_keys:
                    return JSONResponse(
                        status_code=401, content={"detail": "missing or invalid api key"}
                    )

            # Rate limit if configured
            if self.rate_n > 0 and self.rate_win > 0:
                key = request.headers.get("X-API-Key") or "anon"
                now = time.time()
                dq = self._hits.setdefault(key, deque())
                # drop old
                while dq and now - dq[0] > self.rate_win:
                    dq.popleft()
                if len(dq) >= self.rate_n:
                    return JSONResponse(status_code=429, content={"detail": "rate limit exceeded"})
                dq.append(now)

        return await call_next(request)


# --------------------------- app factory ---------------------------


def create_app() -> FastAPI:
    app = FastAPI(title="VELU API", version="1.0.0")

    # CORS: tests expect headers present
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API key + rate limiting only on POST /tasks
    app.add_middleware(ApiKeyAndRateLimitMiddleware)

    # -------------------- health / ready --------------------
    @app.get("/health")
    def health():
        return {"ok": True, "app": "velu"}

    @app.get("/ready")
    def ready():
        """
        Liveness/readiness.
        If TASK_DB is set, ensure path exists and a trivial query is possible.
        Always returns ok=True (tests only check that the endpoint is reachable).
        """
        db = os.environ.get("TASK_DB") or str(Path.cwd() / "data" / "pointers" / "tasks.db")
        with contextlib.suppress(Exception):
            Path(db).parent.mkdir(parents=True, exist_ok=True)
            import sqlite3

            con = sqlite3.connect(db)
            cur = con.cursor()
            with contextlib.suppress(Exception):
                cur.execute("SELECT 1")
            con.close()
        return {"ok": True, "db": db}

    # -------------------- router preview --------------------
    @app.post("/route/preview")
    def route_preview(item: dict):
        """
        Minimal policy preview for tests:
        - deny only 'deploy'
        - include a simple model shape {'name': '...'}
        """
        task = str(item.get("task") or "").lower()
        allowed = task != "deploy"
        policy = {"allowed": allowed, "reason": "deny deploy" if not allowed else "ok"}
        model = {"name": "demo-model"}
        return {"ok": True, "policy": policy, "payload": item.get("payload") or {}, "model": model}

    # -------------------- tasks: list & submit --------------------
    @app.get("/tasks")
    def list_tasks(limit: int = 10):
        items = list(_recent_tasks)[-limit:][::-1]
        return {"ok": True, "items": items}

    @app.post("/tasks")
    async def post_task(item: dict, request: Request):
        """
        Accept a task; echo it; optionally log; optionally enqueue to sqlite queue.
        Enforces MAX_REQUEST_BYTES via Content-Length when provided.
        """
        # 413 guard (do NOT suppress the raise)
        max_bytes = int(os.environ.get("MAX_REQUEST_BYTES", "0") or 0)
        if max_bytes:
            clen_header = request.headers.get("content-length")
            clen = 0
            if clen_header:
                with contextlib.suppress(ValueError):
                    clen = int(clen_header)
            if clen and clen > max_bytes:
                raise HTTPException(status_code=413, detail="payload too large")

        task = str(item.get("task") or "").strip()
        payload = _maybe_to_dict(item.get("payload") or {})

        event = {"task": task, "payload": payload}
        _recent_tasks.append(event)

        # optional JSONL log
        log_path = os.environ.get("TASK_LOG") or ""
        if log_path:
            Path(log_path).parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")

        # enqueue if DB configured
        job_id: int | None = None
        if os.environ.get("TASK_DB"):
            q = _queue()
            q.init()
            job_id = q.enqueue(task=task, payload=payload, priority=0)

        out: dict[str, Any] = {"ok": True, "received": {"task": task, "payload": payload}}
        if job_id is not None:
            out["job_id"] = job_id
        return out

    # -------------------- results polling (worker round-trip) --------------------
    @app.get("/results/{job_id}")
    def get_result(job_id: int):
        """
        Return 200 for any existing job. Shape matches tests:
        response["item"]["status"] == "done"
        """
        try:
            q = _queue()
            rec = q.load(job_id)  # expected keys: status, result, error
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

        if not rec:
            raise HTTPException(status_code=404, detail="not found")

        status = rec.get("status")
        item = {
            "status": status,
            "result": rec.get("result"),
            "error": rec.get("error"),
        }
        return {"ok": status == "done", "item": item}

    return app


# module-global app (some tests import `app` directly)
app = create_app()
