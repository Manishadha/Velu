# ---------- GitHub Actions quick helpers ----------
alias ghv='gh -R Manishadha/Velu'
alias gh-run-id='ghv run list -L 1 --json databaseId -q ".[0].databaseId"'
alias gh-run-summary='RUN_ID=$(gh-run-id); ghv run view "$RUN_ID" --json status,conclusion,displayTitle,headBranch --jq .'
alias gh-job-id='RUN_ID=$(gh-run-id); ghv run view "$RUN_ID" --json jobs -q ".jobs[0].databaseId"'
alias gh-job-steps='RUN_ID=$(gh-run-id); JOB_ID=$(gh-job-id); ghv run view "$RUN_ID" --json jobs -q ".jobs[] | select(.databaseId==$JOB_ID) | {job:.name, steps:(.steps | map({name,status,conclusion}))}"'
alias gh-run-logs='RUN_ID=$(gh-run-id); ghv api /repos/Manishadha/Velu/actions/runs/$RUN_ID/logs > run-$RUN_ID.zip && unzip -p run-$RUN_ID.zip 0_ci.txt | sed -n "1,120p"'
alias gh-job-logs='JOB_ID=$(gh-job-id); ghv api /repos/Manishadha/Velu/actions/jobs/$JOB_ID/logs > job-$JOB_ID.txt && sed -n "1,120p" job-$JOB_ID.txt'
alias velu_pytest='API_KEYS= PYTHONPATH=src pytest -q'
# ---------- velu helpers ----------
velu_use() {
  export TASK_DB="${TASK_DB:-$PWD/.run/jobs.db}"
  export TASK_LOG="${TASK_LOG:-$PWD/.run/tasks.log}"
  export API_KEYS="${API_KEYS:-dev}"
  export VELU_URL="${VELU_URL:-http://127.0.0.1:8010}"
  mkdir -p "$(dirname "$TASK_DB")"
  echo "TASK_DB=$TASK_DB"
  echo "TASK_LOG=$TASK_LOG"
  echo "API_KEYS=$API_KEYS"
  echo "VELU_URL=$VELU_URL"
}

velu_stop() {
  pkill -f "services\.worker\.main" 2>/dev/null || true
  pkill -f "uvicorn .*services\.app_server\.main:create_app" 2>/dev/null || true
  pkill -f "services\.app_server\.main" 2>/dev/null || true
  echo "stopped velu server/worker (if running)"
}

velu_server() {
  velu_use
  pkill -f "uvicorn .*services\.app_server\.main:create_app" 2>/dev/null || true
  nohup uvicorn services.app_server.main:create_app --factory --host 127.0.0.1 --port 8010 \
    >/tmp/velu-server.log 2>&1 &
  echo "server starting (log: /tmp/velu-server.log)"
  # wait for readiness (8s)
  for i in $(seq 1 16); do
    sleep 0.5
    if curl -fsS "$VELU_URL/ready" >/dev/null; then
      echo "server: READY"
      return 0
    fi
    if ! pgrep -f "uvicorn .*services\.app_server\.main:create_app" >/dev/null; then
      echo "server: crashed; last log lines:"; tail -n 80 /tmp/velu-server.log
      return 1
    fi
  done
  echo "server: NOT READY; last log lines:"; tail -n 80 /tmp/velu-server.log
  return 1
}

velu_worker() {
  # usage: velu_worker [MAX_JOBS] (default 50)
  local max="${1:-50}"
  velu_use
  pkill -f "services\.worker\.main" 2>/dev/null || true
  WORKER_ENABLE_PIPELINE=1 WORKER_MAX_JOBS="$max" \
    nohup python -m services.worker.main >/tmp/velu-worker.log 2>&1 &
  echo "worker started (max=$max, log: /tmp/velu-worker.log)"
}

velu_worker_once() {
  # process exactly N jobs then exit
  local n="${1:-1}"
  velu_use
  WORKER_ENABLE_PIPELINE=1 WORKER_MAX_JOBS="$n" python -m services.worker.main
}

velu_tail() {
  tail -n 200 -f /tmp/velu-server.log /tmp/velu-worker.log 2>/dev/null
}

velu_ready() {
  velu_use
  curl -fsS "$VELU_URL/ready" | jq .
}

velu_pipeline() {
  # usage: velu_pipeline [module] [idea...]
  local module="${1:-hello_mod}"; shift || true
  local idea="${*:-demo pipeline}"
  velu_use

  local payload resp
  payload=$(jq -n --arg idea "$idea" --arg module "$module" \
    '{task:"plan", payload:{idea:$idea, module:$module}}')

  resp=$(curl -sS -w '\n%{http_code}' -X POST "$VELU_URL/tasks" \
           -H 'Content-Type: application/json' -H "X-API-Key: $API_KEYS" \
           --data-binary "$payload") || { echo "submit failed (curl error)"; return 1; }

  local body code
  body=$(printf "%s" "$resp" | sed '$!N;$!ba;s/\n\([0-9][0-9][0-9]\)$/\x1F\1/; s/\x1F.*$//')
  code=$(printf "%s" "$resp" | tail -n1)

  if [ "$code" != "200" ]; then
    echo "submit failed (HTTP $code):"
    echo "$body" | jq . || echo "$body"
    return 1
  fi

  local ok job
  ok=$(echo "$body" | jq -r '.ok // empty')
  job=$(echo "$body" | jq -r '.job_id // empty')

  if [ "$ok" != "true" ] || ! [[ "$job" =~ ^[0-9]+$ ]]; then
    echo "server responded without a job_id:"
    echo "$body" | jq . || echo "$body"
    return 1
  fi

  JOB_ID="$job"
  echo "PARENT JOB_ID=$JOB_ID"

  # wait for plan to finish (timeout 120s)
  local limit=$((SECONDS+120))
  until curl -fsS "$VELU_URL/results/$JOB_ID" | jq -e '.item.status=="done"' >/dev/null; do
    [ $SECONDS -gt $limit ] && { echo "timeout waiting for plan"; return 2; }
    sleep 0.5
  done
  CODE_JOB=$(curl -s "$VELU_URL/results/$JOB_ID" | jq -r '.item.result.subjobs.generate_code')
  TEST_JOB=$(curl -s "$VELU_URL/results/$JOB_ID" | jq -r '.item.result.subjobs.run_tests')
  echo "CODE_JOB=$CODE_JOB  TEST_JOB=$TEST_JOB"
}


velu_wait_test() {
  # usage: velu_wait_test <TEST_JOB> [timeout_seconds]
  local tj="$1"; local tmo="${2:-120}"; velu_use
  local limit=$((SECONDS+tmo))
  until curl -fsS "$VELU_URL/results/$tj" | jq -e '.item.status=="done"' >/dev/null; do
    [ $SECONDS -gt $limit ] && { echo "timeout waiting for test job $tj"; return 3; }
    sleep 0.5
  done
  curl -s "$VELU_URL/results/$tj" | jq '.item.result.message, .item.result.stdout'
}

velu_pipeline_full() {
  velu_pipeline "$@" || return $?
  velu_wait_test "$TEST_JOB"
}

velu_result() {
  velu_use
  curl -fsS "$VELU_URL/results/$1" | jq .
}

velu_follow() {
  velu_use
  curl -fsS "$VELU_URL/results/$1?follow=2" | jq .
}


# Re-add virtualenv name to the prompt if active
#_venv_ps1() { [ -n "$VIRTUAL_ENV" ] && printf '(%s) ' "$(basename "$VIRTUAL_ENV")"; }
# Prepend venv banner to your current PS1 (without nuking the rest)
#PS1='$(_venv_ps1)'"$PS1"
# --- velu git helpers ---
velu_git_feature(){ ( cd "${VELU_REPO_PATH:-$PWD}"; make git-feature SCOPE="${1:-misc}" MSG="${2:-feature}" ); }
velu_git_fix(){ ( cd "${VELU_REPO_PATH:-$PWD}"; make git-fix SCOPE="${1:-misc}" MSG="${2:-fix}" ); }
velu_git_chore(){ ( cd "${VELU_REPO_PATH:-$PWD}"; make git-chore SCOPE="${1:-repo}" MSG="${2:-chore}" ); }
velu_git_release(){ ( cd "${VELU_REPO_PATH:-$PWD}"; make git-release VER="${1:-0.1.0}" ); }
