#!/usr/bin/env bash
set -euo pipefail
PASS_FILE="${1:-monitoring/prom_basic_pass.txt}"

if [[ ! -f "$PASS_FILE" ]]; then
  echo "Password file not found: $PASS_FILE"
  echo "Create it from the example:"
  echo "  cp monitoring/prom_basic_pass.txt.example monitoring/prom_basic_pass.txt"
  exit 1
fi

curl -sS -u "admin:$(cat "$PASS_FILE")" http://127.0.0.1/metrics | head -n 30

