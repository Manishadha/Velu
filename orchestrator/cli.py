import argparse
import json
import os
import sys

from orchestrator.router_client import route


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="velu", description="Velu Orchestrator CLI")
    p.add_argument("--task", required=True, help="task name, e.g. plan")
    p.add_argument(
        "--payload",
        default="{}",
        help='JSON payload, e.g. \'{"idea":"hello"}\'',
    )
    p.add_argument(
        "--api",
        default=None,
        help="API base URL (overrides API_URL env), e.g. http://localhost:8000",
    )
    args = p.parse_args(argv)

    if args.api:
        os.environ["API_URL"] = args.api

    try:
        payload = json.loads(args.payload or "{}")
    except Exception as e:
        print(f"invalid JSON for --payload: {e}", file=sys.stderr)
        return 2

    result = route({"task": args.task, "payload": payload})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
