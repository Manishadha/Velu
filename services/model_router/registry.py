from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ModelChoice:
    name: str
    provider: str
    params: dict[str, Any]


def choose(task: dict[str, Any]) -> ModelChoice:
    # Minimal, deterministic stub for now
    return ModelChoice(
        name="mini-phi",
        provider="local",
        params={"temperature": 0.2, "max_tokens": 512},
    )
