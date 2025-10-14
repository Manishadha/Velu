# Velu Architecture (2025)

- **orchestrator/**: agent contracts, router client, scheduler, state.
- **services/**: model-router, policy-engine, feedback-monitor (sidecars).
- **agents/**: planning, architecture, codegen, executor, debug, security, ui, build, deploy.
- **data/**: models (immutable), pointers (current), rules (versioned), threat-intel (mirrors).
- **ops/**: env configs (hot-reload), Docker, CI/CD, optional Kubernetes.

**Update Strategy (no code change):** stable APIs + adapters, config-driven behavior, sidecars, immutable artifacts with movable pointers; canary/shadow/blue-green.

--------------------------------

VELU PROJECT ARCHIVE & OPERATING GUIDE (2025)

Status: working end-to-end (app + worker + Caddy + Prometheus + Grafana)
Goal: Local-first AI task orchestrator with agents (plan → analyze → execute → report), observable via Prometheus/Grafana, minimal external dependencies.

OVERVIEW

VELU orchestrates structured tasks through specialized agents, routes them using a model router (local-first), tracks jobs in SQLite, and exposes health/metrics for observability.

Local-first: defaults to llama.cpp/llamafile/starcoder; OpenAI key optional.
Agents included: planner, analyzer, executor, reporter.
Ops: reverse proxy with Caddy, metrics protected with Basic Auth, Prometheus scrape, Grafana dashboards, SQLite backups.

REPOSITORY LAYOUT (TARGET STRUCTURE)

orchestrator/ agent contracts, router client, scheduler, state
services/ model-router, policy-engine, feedback-monitor (sidecars)
agents/ planning, architecture, codegen, executor, debug, security, ui, build, deploy
data/ models (immutable), pointers (current), rules (versioned), threat-intel (mirrors)
ops/ env configs (hot-reload), Docker, CI/CD, optional Kubernetes

ARCHITECTURE

Services:

app: FastAPI server (endpoints: /tasks, /results/{id}, /metrics, /health, /ui/submit, /route/preview)

worker: background consumer of the SQLite queue

caddy: reverse proxy, protects /metrics with basic auth

prometheus: scrapes caddy:80/metrics

grafana: dashboards from Prometheus

sqlite_backup: periodic copies of /data/jobs.db

Data flow:

Client posts task to app → SQLite.

Worker runs agent handler → result.

App exposes results + metrics.

Caddy protects /metrics (basic auth).

Prometheus scrapes; Grafana visualizes.

CONFIGURATION

Example .env
API_KEYS=devkey123
CORS_ORIGINS=http://localhost,http://127.0.0.1

HOST=0.0.0.0
PORT=8000
TASK_DB=/data/jobs.db
OPENAI_API_KEY=
MODEL_ROUTER_CONFIG=configs/models.yml

Model config (configs/models.yml)
default:
name: mini-phi
provider: local
params:
temperature: 0.2
max_tokens: 512

routes:
plan:
name: llamafile-plan
provider: llamafile
params:
temperature: 0.2
analyze:
name: llama.cpp-analyze
provider: llama.cpp
params:
ctx: 8192
execute:
name: local-exec
provider: local
params: {}
report:
name: mini-phi
provider: local
params:
temperature: 0.2

CHAT BEHAVIOR PROFILE 2025

Purpose:
PhD-level reasoning protocol for collaboration with AI systems. Ensures each response is grounded, structured, current, and minimal error.

Core Principles:

THINK → VALIDATE → CODE
Never start with code. Explain logic first.

ACADEMIC PRECISION
Post-grad rigor, tested logic, explicit failures.

STABILITY BEFORE SPEED
Prefer maintainable over quick.

CONTEXTUAL AWARENESS
Keep context accurate, reuse it.

HUMAN-CENTERED CLARITY
Technical English, no filler.

MODERNITY
Use 2025 syntax and tools. Deprecate old syntax.

ERROR INTELLIGENCE
Identify → Explain → Fix → Verify.

ACTIONABLE OUTPUTS
End every reply with executable next steps.

ITERATIVE COHERENCE
Build logically, no regressions.

EVIDENCE VALIDATION
Show outputs or logs before claiming success.

Interaction Style:
Tone: direct, expert, non-verbose.
Sections: RESULT, CAUSE, FIX, REASON.
Always include tested, working commands.

Conduct Rules:
Never delete user code.
Don’t reformat working code unless asked.
Test before commit.
Always specify container names in Docker.
Commit format:
git add .
git commit -m "feat(...): clear message"
git push
Use curl and jq for API checks.
Verify health before rebuilds.

FEATURES IMPLEMENTED

Agents: plan, analyze, execute, report
Queue worker and fallback DB mode
/ui/submit page and polling
/route/preview route
Prometheus metrics middleware
Caddy basic_auth with bcrypt
Prometheus scrape with file auth
Grafana dashboards
SQLite backup automation

DEBUG & FIX LOG

401 on scrape – fixed with Caddy bcrypt + password file.
405 HEAD method – use GET instead.
502 Bad Gateway – wait for app healthy or verify DNS.
Prometheus target down → up after auth fix.
Grafana Angular panel – remove Angular, use JSON panel.
Pre-commit ruff issues – updated syntax.
submit_task.sh JSON errors – used --data-binary properly.

COMMANDS

Start:
docker compose up -d --build app worker caddy prometheus grafana

Health/UI:
curl -s http://127.0.0.1/health

curl -s http://127.0.0.1/ui/submit
 | head -n1

Metrics:
curl -s -u "admin:$(cat monitoring/prom_basic_pass.txt)" http://127.0.0.1/metrics
 | head

Prometheus Targets:
curl -s 'http://localhost:9090/api/v1/targets
' | jq '.data.activeTargets[]? | {scrapeUrl,health,lastError}'

Agent test:
API=127.0.0.1:8000
KEY=devkey123

jid_plan=$(curl -s -X POST http://$API/tasks -H 'content-type: application/json' -H "x-api-key: $KEY" --data-binary '{"task":"plan","payload":{"goal":"hello world"}}' | jq -r .job_id)
jid_analyze=$(curl -s -X POST http://$API/tasks -H 'content-type: application/json' -H "x-api-key: $KEY" --data-binary '{"task":"analyze","payload":{"text":"some logs"}}' | jq -r .job_id)
jid_execute=$(curl -s -X POST http://$API/tasks -H 'content-type: application/json' -H "x-api-key: $KEY" --data-binary '{"task":"execute","payload":{"cmd":"echo hi"}}' | jq -r .job_id)
jid_report=$(curl -s -X POST http://$API/tasks -H 'content-type: application/json' -H "x-api-key: $KEY" --data-binary '{"task":"report","payload":{"title":"Build report","data":{"ok":true}}}' | jq -r .job_id)

for jid in "$jid_plan" "$jid_analyze" "$jid_execute" "$jid_report"; do
for i in {1..12}; do
out=$(curl -s "http://$API/results/$jid")
if jq -e '.item.status == "done"' >/dev/null <<<"$out"; then
echo "$out" | jq .
break
fi
sleep 0.5
done
done

Route preview:
curl -s -X POST http://127.0.0.1:8000/route/preview
 -H 'content-type: application/json' -H 'x-api-key: devkey123' --data-binary '{"task":"plan","payload":{"goal":"hello"}}' | jq .

Rotate metrics password:
openssl rand -base64 32 > monitoring/prom_basic_pass.txt
PASS="$(tr -d '\n' < monitoring/prom_basic_pass.txt)"
HASH="$(docker run --rm caddy:2 caddy hash-password --plaintext "$PASS")"
Update Caddyfile with HASH
docker compose up -d caddy prometheus

PERFORMANCE & STABILITY

Prometheus/Grafana: remove Angular panels, tune retention.
App: sample metrics if load high.
ChatGPT: archive long chats, start new with the behavior profile.

FINAL GOAL OF VELU

A modular, local-first agent orchestrator that:

Accepts structured tasks via API/UI

Routes to domain agents (planning, analysis, execution, reporting, later: architecture, codegen, debug, security, UI, build, deploy)

Executes without external GPT dependency

Surfaces health & metrics via Prometheus

Visualizes with Grafana

Auto-backs up data

Evolves toward orchestrator/services/agents/data/ops structure with CI/CD and hot reload.

NEXT STEPS

Add new agents (codegen, security, etc.)

Expand models.yml for each agent

Polish UI (submit + results)

Add CI/CD in ops/

Keep this doc updated as single source of truth.

COMMIT THIS DOC

mkdir -p docs
cp VELU_PROJECT_ARCHIVE.txt docs/VELU_PROJECT_ARCHIVE.txt
git add docs/VELU_PROJECT_ARCHIVE.txt
git commit -m "docs: VELU project archive & chat behavior profile (2025)"
git push

