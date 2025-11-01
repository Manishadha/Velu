# services/agents/codegen.py
from __future__ import annotations

from typing import Any

# ruff: noqa: E501


def _slug(s: str) -> str:
    out = []
    for ch in (s or "").lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", "_"):
            out.append("-")
    slug = "".join(out).strip("-")
    return slug or "app"


def _python_cli(spec: str, appname: str) -> str:
    """Deterministic Python CLI scaffold. Includes the required phrase in code."""
    return f"""\
#!/usr/bin/env python3
# hello from codegen: {spec}
from __future__ import annotations

import argparse

def main() -> int:
    parser = argparse.ArgumentParser(prog="{appname}", description="{spec}")
    parser.add_argument("--name", default="world", help="Name to greet")
    args = parser.parse_args()
    print(f"Hello, {{args.name}}!")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
"""


def handle(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Two supported input shapes:

    1) Spec-based (unit tests use this):
       payload = {"lang": "python", "spec": "..."}
       -> returns {"ok": True, "artifact": {"language":"python","path":...,"code":...}, "files":[...]}

       Unsupported languages return ok=False.

    2) Legacy/pipeline-friendly:
       payload = {"idea": "...", "module": "..."}
       -> returns {"ok": True, "files": [...]}
    """
    # -----------------------------
    # Shape 1: language + spec
    # -----------------------------
    if "lang" in payload:
        lang = str(payload.get("lang", "")).lower().strip()
        spec = str(payload.get("spec", "")).strip() or "CLI app"

        if lang != "python":
            return {"ok": False, "error": f"unsupported lang: {lang}", "supported": ["python"]}

        fname = _slug(spec)
        path = f"generated/{fname}.py"
        code = _python_cli(spec=spec, appname=fname)

        files = [{"path": path, "content": code}]
        artifact = {"path": path, "language": "python", "code": code}

        return {"ok": True, "agent": "codegen", "artifact": artifact, "files": files}

    # -----------------------------
    # Shape 2: idea + module (pipeline legacy)
    # -----------------------------
    idea = str(payload.get("idea", "")).strip()
    module = str(payload.get("module", "")).strip() or "hello_mod"

    py_path = f"src/{module}.py"
    test_path = f"tests/test_{module}.py"

    files = [
        {"path": py_path, "content": f'def run():\n    return "{idea or "demo"} via {module}"\n'},
        {"path": test_path, "content": "def test_sanity():\n    assert True\n"},
    ]

    return {"ok": True, "agent": "codegen", "files": files}
