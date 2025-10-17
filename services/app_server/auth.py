# services/app_server/auth.py
import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


def _keys() -> dict[str, str]:
    # Format: API_KEYS="k1:dev,k2:ops,k3"
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
    # protect write/modify endpoints; allow health & reads
    return method.upper() == "POST" and path.startswith("/tasks")


def _rate_key_for_api_key(request: Request) -> tuple[str, str]:
    # Rate limit key + label. If API key present, prefer it.
    api_key = request.headers.get("x-api-key") or ""
    if api_key and api_key in _keys():
        return (f"apk:{api_key[:6]}…", _keys()[api_key])
    # fallback to IP bucket
    fwd = request.headers.get("x-forwarded-for")
    host = (
        fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")
    )
    return (f"ip:{host}", "ip")


class ApiKeyRequiredMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Always allow health/preflight
        if request.method == "OPTIONS" or request.url.path == "/health":
            return await call_next(request)

        if not _need_auth(request.url.path, request.method):
            # Tell rate-limiter to use API-key bucket if present
            request.state.rate_bucket, request.state.rate_label = _rate_key_for_api_key(request)
            return await call_next(request)

        keys = _keys()
        # If no keys configured, allow all (development mode)
        if not keys:
            request.state.rate_bucket, request.state.rate_label = _rate_key_for_api_key(request)
            return await call_next(request)

        provided = request.headers.get("x-api-key")
        if not provided or provided not in keys:
            return JSONResponse({"detail": "missing or invalid api key"}, status_code=401)

        request.state.rate_bucket, request.state.rate_label = (
            f"apk:{provided[:6]}…",
            keys[provided],
        )
        return await call_next(request)
