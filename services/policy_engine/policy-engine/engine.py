from __future__ import annotations

import glob
import json
import os
from typing import Any

RULES_DIR = os.environ.get("RULES_DIR", "data/rules")

_last_scan = 0.0
_cache: list[dict[str, Any]] = []


def _scan() -> list[dict[str, Any]]:
    global _last_scan, _cache
    try:
        latest = max(
            [os.path.getmtime(p) for p in glob.glob(os.path.join(RULES_DIR, "*.json"))]
            + [0.0]
        )
    except ValueError:
        latest = 0.0
    if latest > _last_scan:
        packs = []
        for p in sorted(glob.glob(os.path.join(RULES_DIR, "*.json"))):
            try:
                with open(p, encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        packs.append(data)
            except (ValueError, KeyError, TypeError, OSError):
                continue
        _cache = packs
        _last_scan = latest
    return _cache


def evaluate(
    task: dict[str, Any], context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Very simple allow/deny evaluator.
    Structure of a rule pack:
      {"name":"baseline","deny":[{"task":"deploy"}],"allow":[{"task":"plan"}]}
    First matching deny wins. Then allow. Else default allow=true.
    """
    packs = _scan()
    name = (task.get("task") or "").lower()
    for pack in packs:
        for rule in pack.get("deny", []):
            if (rule.get("task") or "").lower() == name:
                return {"allowed": False, "pack": pack.get("name", ""), "rule": rule}
    for pack in packs:
        for rule in pack.get("allow", []):
            if (rule.get("task") or "").lower() == name:
                return {"allowed": True, "pack": pack.get("name", ""), "rule": rule}
    return {"allowed": True, "pack": None, "rule": None}
