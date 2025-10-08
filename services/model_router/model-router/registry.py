from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import yaml

CONFIG = os.environ.get("MODEL_ROUTER_CONFIG", "configs/models.yml")
_last = 0.0
_cache: dict[str, Any] = {}


@dataclass
class ModelChoice:
    name: str
    provider: str
    params: dict[str, Any]


def _load() -> dict[str, Any]:
    global _last, _cache
    try:
        mtime = os.path.getmtime(CONFIG)
    except FileNotFoundError:
        return {}
    if mtime > _last:
        with open(CONFIG, encoding="utf-8") as f:
            _cache = yaml.safe_load(f) or {}
        _last = mtime
    return _cache


def choose(task: dict[str, Any], context: dict[str, Any] | None = None) -> ModelChoice:
    """
    Simple rules:
      - task.task can map to a route in models.yml
      - fallback to default
    Hot-reloads when the YAML changes.
    """
    cfg = _load()
    routes = cfg.get("routes") or {}
    default = cfg.get("default") or {
        "name": "local-llm",
        "provider": "llama.cpp",
        "params": {},
    }

    key = (task.get("task") or "").lower().strip()
    picked = routes.get(key, default)
    return ModelChoice(
        name=picked.get("name", "local-llm"),
        provider=picked.get("provider", "llama.cpp"),
        params=picked.get("params") or {},
    )
