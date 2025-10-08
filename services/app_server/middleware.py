# services/app_server/middleware.py
import os
import time
from collections import deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    def _max_bytes(self) -> int:
        return int(os.environ.get("MAX_REQUEST_BYTES", "1048576"))

    async def dispatch(self, request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH"):
            # read and re-inject the body with a size check
            body = await request.body()
            if len(body) > self._max_bytes():
                return JSONResponse({"detail": "payload too large"}, status_code=413)

            async def receive():
                return {"type": "http.request", "body": body, "more_body": False}

            return await call_next(Request(scope=request.scope, receive=receive))
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Per-bucket sliding-window limiter.
    Buckets:
      - If X-API-Key present:   "apk:<value>"   (per key)
      - Else if auth set state: request.state.rate_bucket
      - Else:                   client IP
    Behavior:
      - Pre-check window; if already >= limit -> 429
      - Call downstream
      - If response is 401 -> don't count
      - Else -> record a hit and return response
    """

    def __init__(self, app):
        super().__init__(app)
        self.hits: dict[str, deque[float]] = {}

    def _bucket_for(self, request: Request) -> str:
        # Prefer explicit API key header (guarantees per-key isolation)
        hdr_key = request.headers.get("x-api-key")
        if hdr_key:
            return f"apk:{hdr_key}"

        # Otherwise prefer bucket set by auth middleware (if any)
        if hasattr(request.state, "rate_bucket") and request.state.rate_bucket:
            return request.state.rate_bucket

        # Fallback to client IP
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return f"ip:{fwd.split(',')[0].strip()}"
        return f"ip:{request.client.host if request.client else 'unknown'}"

    def _limits(self) -> tuple[int, int]:
        # allowed, window_seconds
        return (
            int(os.environ.get("RATE_REQUESTS", "60")),
            int(os.environ.get("RATE_WINDOW_SEC", "60")),
        )

    async def dispatch(self, request: Request, call_next):
        bucket = self._bucket_for(request)
        allowed, window = self._limits()

        now = time.time()
        dq = self.hits.setdefault(bucket, deque())

        # purge old hits
        while dq and (now - dq[0]) > window:
            dq.popleft()

        # PRE-CHECK: already at or over quota?
        if len(dq) >= allowed:
            return JSONResponse({"detail": "rate limit exceeded"}, status_code=429)

        # Run downstream
        response = await call_next(request)

        # Don't count unauthorized attempts
        if getattr(response, "status_code", 200) == 401:
            return response

        # Record this authorized request
        t = time.time()
        dq.append(t)
        # purge again (strictness)
        while dq and (t - dq[0]) > window:
            dq.popleft()

        return response
