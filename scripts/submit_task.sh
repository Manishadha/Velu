#!/usr/bin/env bash
# Usage:
#   ./scripts/submit_task.sh devkey123 plan '{"demo":1}'
#   ./scripts/submit_task.sh devkey123 plan /tmp/payload.json

set -Eeuo pipefail
trap 'echo "❌ failed (exit $?) on line $LINENO" >&2' ERR

API_KEY="${1:-${API_KEY:-devkey123}}"
TASK="${2:-plan}"
ARG="${3:-{\"demo\":1}}"

read_payload() {
  local src="$1"
  if [[ -f "$src" ]]; then
    cat -- "$src"
  else
    printf '%s' "$src"
  fi
}

RAW="$(read_payload "$ARG")"

# Try to build the request body with jq; if it fails and we see an extra trailing "}",
# drop exactly one "}" and try again.
build_body() {
  local payload="$1"
  jq -cn --arg task "$TASK" --argjson payload "$payload" '{task:$task, payload:$payload}'
}

if ! BODY="$(build_body "$RAW" 2>/dev/null)"; then
  if [[ "$RAW" =~ \}$ ]]; then
    RAW_FIXED="${RAW%}"}   # remove one trailing }
    if BODY="$(build_body "$RAW_FIXED" 2>/dev/null)"; then
      echo "⚠️  fixed a trailing '}' in payload" >&2
    else
      echo "ERROR: payload is not valid JSON" >&2
      echo "Raw bytes (hex):" >&2
      printf '%s' "$RAW" | od -An -tx1 | sed 's/^/  /' >&2
      exit 11
    fi
  else
    echo "ERROR: payload is not valid JSON" >&2
    echo "Raw bytes (hex):" >&2
    printf '%s' "$RAW" | od -An -tx1 | sed 's/^/  /' >&2
    exit 11
  fi
fi

echo "→ POST /tasks  (task=$TASK)"
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
curl -sS --noproxy 127.0.0.1,localhost \
  -X POST "http://127.0.0.1:8000/tasks" \
  -H "content-type: application/json" \
  -H "x-api-key: ${API_KEY}" \
  --data-binary "$BODY"
echo
