# services/app_server/middleware.py
import os
import time
from collections import deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


def _max_bytes() -> int:
    return int(os.environ.get("MAX_REQUEST_BYTES", str(1 * 1024 * 1024)))  # default 1MB


def _rate_conf() -> tuple[int, int]:
    return (
        int(os.environ.get("RATE_REQUESTS", "30")),
        int(os.environ.get("RATE_WINDOW_SEC", "60")),
    )


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Let preflight/health pass quickly
        if request.method == "OPTIONS" or request.url.path == "/health":
            return await call_next(request)
        # Content-Length short-circuit
        cl = request.headers.get("content-length")
        max_bytes = _max_bytes()
        if cl and cl.isdigit() and int(cl) > max_bytes:
            return JSONResponse({"detail": "payload too large"}, status_code=413)
        # Fallback to reading the body
        body = await request.body()
        if len(body) > max_bytes:
            return JSONResponse({"detail": "payload too large"}, status_code=413)
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.hits: dict[str, deque[float]] = {}

    def _key(self, request: Request) -> str:
        fwd = request.headers.get("x-forwarded-for")
        return (
            fwd.split(",")[0].strip()
            if fwd
            else (request.client.host if request.client else "unknown")
        )

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" or request.url.path == "/health":
            return await call_next(request)
        now = time.time()
        key = self._key(request)
        q = self.hits.setdefault(key, deque())
        rate, window = _rate_conf()
        # drop old
        while q and (now - q[0]) > window:
            q.popleft()
        if len(q) >= rate:
            return JSONResponse({"detail": "rate limit exceeded"}, status_code=429)
        q.append(now)
        return await call_next(request)
