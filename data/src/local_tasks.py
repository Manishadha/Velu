# data/src/local_tasks.py
from __future__ import annotations
from typing import Any


def plan(payload: dict[str, Any]) -> dict[str, Any]:
    idea = str(payload.get("idea", "demo"))
    module = str(payload.get("module", "hello_mod"))
    return {"ok": True, "plan": f"{idea} via {module}"}


def codegen(payload: dict[str, Any]) -> dict[str, Any]:
    idea = str(payload.get("idea", "demo"))
    module = str(payload.get("module", "hello_mod"))

    files: list[dict[str, str]] = [
        {
            "path": f"{module}/__init__.py",
            "content": "# generated package\n",
        },
        {
            "path": f"{module}/main.py",
            "content": ("def run():\n" f'    return "{idea} via {module}"\n'),
        },
        {
            "path": f"tests/test_{module}.py",
            "content": ("def test_sanity():\n" "    assert True\n"),
        },
    ]
    return {"ok": True, "files": files}


# Back-compat: allow callers that still send `generate_code`
def generate_code(payload: dict[str, Any]) -> dict[str, Any]:
    return codegen(payload)
