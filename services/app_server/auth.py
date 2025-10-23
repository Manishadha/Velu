from __future__ import annotations

import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


def _keys() -> dict[str, str]:
    """
    Parse API_KEYS env var like:
      API_KEYS="k1:dev,k2:ops,k3"
    -> {"k1":"dev","k2":"ops","k3":"default"}
    """
    raw = os.environ.get("API_KEYS", "").strip()
    if not raw:
        return {}
    out: dict[str, str] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            k, label = part.split(":", 1)
            out[k.strip()] = label.strip() or "default"
        else:
            out[part] = "default"
    return out


def _need_auth(path: str, method: str) -> bool:
    # Always allow health/ready
    if path in ("/health", "/ready"):
        return False
    # Protect only POST /tasks
    return method.upper() == "POST" and path.startswith("/tasks")


def _rate_key_for_api_key(request: Request) -> tuple[str, str]:
    # Rate limit key + label. Prefer API key if present.
    api_key = request.headers.get("x-api-key") or ""
    keys = _keys()
    if api_key and api_key in keys:
        return (f"apk:{api_key[:6]}…", keys[api_key])

    fwd = request.headers.get("x-forwarded-for")
    host = (
        fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")
    )
    return (f"ip:{host}", "ip")


class ApiKeyRequiredMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Always allow CORS preflight + health/ready
        if request.method == "OPTIONS" or request.url.path in ("/health", "/ready"):
            return await call_next(request)

        # Set rate bucket early (used by limiter)
        request.state.rate_bucket, request.state.rate_label = _rate_key_for_api_key(request)

        if not _need_auth(request.url.path, request.method):
            return await call_next(request)

        keys = _keys()

        # If no keys configured, permissive mode
        if not keys:
            return await call_next(request)

        provided = request.headers.get("x-api-key", "")
        if provided not in keys:
            # tests assert on this exact string:
            return JSONResponse({"detail": "missing or invalid api key"}, status_code=401)

        # Good key — tag bucket with key label
        request.state.rate_bucket = f"apk:{provided[:6]}…"
        request.state.rate_label = keys[provided]
        return await call_next(request)
