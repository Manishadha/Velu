#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import time

from jose import jwt

secret = os.environ.get("JWT_SECRET", "dev-secret-change-me")
aud = os.environ.get("JWT_AUDIENCE", "velu-api")
iss = os.environ.get("JWT_ISSUER", "velu")
alg = os.environ.get("JWT_ALG", "HS256")

now = int(time.time())
claims = {
    "sub": "ops@example.com",
    "iss": iss,
    "aud": aud,
    "iat": now,
    "exp": now + 3600,  # 1h
    "scope": "tasks:write",
}
token = jwt.encode(claims, secret, algorithm=alg)
print(json.dumps({"token": token}, indent=2))
