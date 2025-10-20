# 🧠 Velu — Task Orchestrator & Metrics API

FastAPI-based task queue, routing, and policy evaluation system with Prometheus monitoring.

![CI](https://github.com/Manishadha/velu/actions/workflows/ci.yml/badge.svg)


Self-hosted, multi-agent AI pipeline that plans → codes → tests → secures → builds → deploys → monitors.

---



### Local (for development)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
bash scripts/test.sh  # all tests should pass

### 🔐 Prometheus basic auth

Prometheus scrapes `/metrics` through Caddy with basic auth.

1. Copy the example and set your own password (plaintext, single line):
   ```bash
   cp monitoring/prom_basic_pass.txt.example monitoring/prom_basic_pass.txt
   echo "my-SUPER-strong-password" > monitoring/prom_basic_pass.txt

# Smoke test: enqueue 4 tasks, then poll results & check Prometheus
API=127.0.0.1:8000 KEY=devkey123

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
  for i in {1..12}; do
    out=$(curl -s "http://$API/results/$jid")
    jq -e '.item.status=="done"' >/dev/null <<<"$out" && echo "$out" | jq '.item|{id,status,task,result}' && break
    sleep 0.5
  done
done

curl -s 'http://localhost:9090/api/v1/targets' | jq '.data.activeTargets[]? | {scrapeUrl,health,lastError}'

Auto-merge smoke test
