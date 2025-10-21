from __future__ import annotations

import os
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# ------------------------------------------------------------------------------
# Config
# ------------------------------------------------------------------------------
# Modes:
#   - "strict" (default): enforce API key or valid JWT on protected endpoints
#   - "permissive"       : bypass auth (used by CI/tests/dev)
AUTH_MODE = os.getenv("AUTH_MODE", "strict").strip().lower()

# API keys: "k1:dev,k2:ops,k3"
def _keys() -> dict[str, str]:
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
            out[k.strip()] = (label.strip() or "default")
        else:
            out[part] = "default"
    return out


# Optional JWT (only if JWT_SECRET is set and python-jose is installed)
_JWT_SECRET = os.getenv("JWT_SECRET", "").strip()
_JWT_AUD = os.getenv("JWT_AUDIENCE", "velu-api").strip()
_JWT_ISS = os.getenv("JWT_ISSUER", "velu").strip()
_JWT_ALG = os.getenv("JWT_ALG", "HS256").strip()

try:
    from jose import JWTError, jwt  # type: ignore
except Exception:  # pragma: no cover - jose not installed
    JWTError = Exception  # type: ignore
    jwt = None  # type: ignore


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
def _need_auth(path: str, method: str) -> bool:
    # protect write/modify endpoints; allow health & reads
    return method.upper() == "POST" and path.startswith("/tasks")


def _rate_key_for_api_key(request: Request) -> tuple[str, str]:
    # Rate limit key + label. If API key present, prefer it.
    api_key = request.headers.get("x-api-key") or ""
    keys = _keys()
    if api_key and api_key in keys:
        return (f"apk:{api_key[:6]}…", keys[api_key])

    # fallback to IP bucket
    fwd = request.headers.get("x-forwarded-for")
    host = (
        fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")
    )
    return (f"ip:{host}", "ip")


def _has_valid_api_key(request: Request) -> bool:
    provided = request.headers.get("x-api-key")
    return bool(provided and provided in _keys())


def _has_valid_jwt(request: Request) -> bool:
    """Validate Authorization: Bearer <JWT> **iff** JWT secret + jose are available."""
    if not _JWT_SECRET or jwt is None:
        return False

    auth = request.headers.get("authorization") or ""
    if not auth.startswith("Bearer "):
        return False

    token = auth.split(" ", 1)[1].strip()
    try:
        claims = jwt.decode(
            token,
            _JWT_SECRET,
            algorithms=[_JWT_ALG],
            audience=_JWT_AUD if _JWT_AUD else None,
            options={"require_aud": bool(_JWT_AUD)},
        )
    except JWTError:
        return False

    if _JWT_ISS and claims.get("iss") != _JWT_ISS:
        return False

    now = int(time.time())
    exp = claims.get("exp")
    return not (exp is not None and int(exp) < now)



# ------------------------------------------------------------------------------
# Middleware
# ------------------------------------------------------------------------------
class ApiKeyRequiredMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Always allow health/preflight
        if request.method == "OPTIONS" or request.url.path in ("/health", "/ready"):
            return await call_next(request)

        # Permissive mode fully bypasses auth (keeps CI/tests green)
        if AUTH_MODE == "permissive":
            request.state.rate_bucket, request.state.rate_label = _rate_key_for_api_key(request)
            return await call_next(request)

        # Unprotected path? continue, but still set a rate bucket
        if not _need_auth(request.url.path, request.method):
            request.state.rate_bucket, request.state.rate_label = _rate_key_for_api_key(request)
            return await call_next(request)

        # Strict mode from here: require valid API key OR JWT
        keys = _keys()
        # If neither API keys nor JWT secret are configured, allow (dev-friendly)
        if not keys and not _JWT_SECRET:
            request.state.rate_bucket, request.state.rate_label = _rate_key_for_api_key(request)
            return await call_next(request)

        if _has_valid_api_key(request) or _has_valid_jwt(request):
            request.state.rate_bucket, request.state.rate_label = _rate_key_for_api_key(request)
            return await call_next(request)

        return JSONResponse({"detail": "missing or invalid credentials"}, status_code=401)
