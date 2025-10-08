from __future__ import annotations

from typing import Any

SAFE_LANGS: set[str] = {"python", "bash", "javascript", "typescript"}


def handle(_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Deterministic local code generator (scaffold/boilerplate)."""
    lang = str(payload.get("lang", "python")).lower()
    spec = str(payload.get("spec", "hello world"))

    if lang not in SAFE_LANGS:
        return {"ok": False, "error": f"unsupported lang: {lang}", "data": {}}

    if lang == "python":
        code = (
            f'"""Auto-generated: {spec}"""\n'
            "def main():\n"
            f'    print("hello from codegen: {spec}")\n'
            "\n"
            'if __name__ == "__main__":\n'
            "    main()\n"
        )
    elif lang == "bash":
        code = (
            "#!/usr/bin/env bash\n"
            f"# Auto-generated: {spec}\n"
            f'echo "hello from codegen: {spec}"\n'
        )
    else:  # javascript / typescript
        code = (
            f"// Auto-generated: {spec}\n"
            "export function main() {\n"
            f'  console.log("hello from codegen: {spec}");\n'
            "}\n"
            'if (typeof require !== "undefined" && require.main === module) {\n'
            "  main();\n"
            "}\n"
        )

    return {"ok": True, "artifact": {"language": lang, "code": code}}
