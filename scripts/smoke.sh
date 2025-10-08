#!/usr/bin/env bash
set -euo pipefail
API=${API:-127.0.0.1:8000}
KEY=${KEY:-devkey123}

jid_plan=$(curl -s -X POST http://$API/tasks -H 'content-type: application/json' -H "x-api-key: $KEY" \
  --data-binary '{"task":"plan","payload":{"goal":"hello world"}}' | jq -r .job_id)
jid_analyze=$(curl -s -X POST http://$API/tasks -H 'content-type: application/json' -H "x-api-key: $KEY" \
  --data-binary '{"task":"analyze","payload":{"text":"some logs"}}' | jq -r .job_id)
jid_execute=$(curl -s -X POST http://$API/tasks -H 'content-type: application/json' -H "x-api-key: $KEY" \
  --data-binary '{"task":"execute","payload":{"cmd":"echo hi"}}' | jq -r .job_id)
jid_report=$(curl -s -X POST http://$API/tasks -H 'content-type: application/json' -H "x-api-key: $KEY" \
  --data-binary '{"task":"report","payload":{"title":"Build report","data":{"ok":true}}}' | jq -r .job_id)

echo "plan=$jid_plan analyze=$jid_analyze execute=$jid_execute report=$jid_report"

for jid in "$jid_plan" "$jid_analyze" "$jid_execute" "$jid_report"; do
  echo "== polling $jid =="
  for i in {1..12}; do
    out=$(curl -s "http://$API/results/$jid")
    if jq -e '.item.status == "done"' >/dev/null <<<"$out"; then
      echo "$out" | jq '.item | {id,status,task,result}'
      break
    fi
    sleep 0.5
  done
done

echo "== prometheus target =="
curl -s 'http://localhost:9090/api/v1/targets' \
  | jq '.data.activeTargets[]? | {scrapeUrl, health, lastError}'
