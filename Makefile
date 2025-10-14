# Use ">" as the recipe prefix so we don't rely on literal tab characters
.RECIPEPREFIX := >

SHELL := /bin/bash

# ---- shared env --------------------------------------------------------------
export VELU_URL ?= http://127.0.0.1:8010
export TASK_DB  ?= $(PWD)/.run/jobs.db
export TASK_LOG ?= $(PWD)/.run/tasks.log
export API_KEYS ?= dev

APP  ?= velu
PORT ?= 8000
IMAGE ?= $(APP):latest

.PHONY: help
help:
> @echo "Targets:"
> @echo "  up              - start velu server (uvicorn) and wait for /ready"
> @echo "  down            - stop server & worker"
> @echo "  worker          - background worker; N=<jobs> (default 25)"
> @echo "  plan            - submit demo pipeline and print job ids"
> @echo "  follow          - follow a job (JOB_ID=<id>)"
> @echo "  test            - run pytest with API_KEYS unset"
> @echo "  fmt             - run formatters (optional)"
> @echo "  lint            - run linters (optional)"
> @echo "  docker-up       - compose up (all services)"
> @echo "  docker-down     - compose down"
> @echo "  docker-logs     - compose logs -f"
> @echo "  docker-rebuild  - build no-cache & up --force-recreate"
> @echo "  api             - run uvicorn (dev) on $(PORT)"
> @echo "  docker-build    - docker build -t $(IMAGE)"
> @echo "  docker-run      - docker run image mapping $(PORT):8000"

# ---- velu local helpers ------------------------------------------------------
.PHONY: up
up:
> @bash -ic 'velu_server'

.PHONY: down
down:
> @bash -ic 'velu_stop'

.PHONY: worker
worker:
> @bash -ic 'velu_worker $${N:-25}'

.PHONY: plan
plan:
> @bash -ic 'velu_pipeline hello_mod "demo pipeline"'

.PHONY: follow
follow:
> @curl -fsS "$(VELU_URL)/results/$(JOB_ID)?follow=2" | jq .

.PHONY: test
test:
> @env -u API_KEYS PYTHONPATH=src pytest -q

.PHONY: fmt
fmt:
> @python -m black services || true

.PHONY: lint
lint:
> @python -m ruff services || true

# ---- docker / compose helpers ------------------------------------------------
.PHONY: docker-up
docker-up:
> docker compose up -d

.PHONY: docker-down
docker-down:
> docker compose down

.PHONY: docker-logs
docker-logs:
> docker compose logs -f --tail=200

.PHONY: docker-rebuild
docker-rebuild:
> docker compose build --no-cache
> docker compose up -d --force-recreate

# ---- raw uvicorn / docker image targets -------------------------------------
.PHONY: api
api:
> uvicorn services.app_server.main:app --host 0.0.0.0 --port $(PORT) --reload

.PHONY: docker-build
docker-build:
> docker build -t $(IMAGE) .

.PHONY: docker-run
docker-run:
> docker run --rm -p $(PORT):8000 \
>   -e CORS_ORIGINS=http://localhost:3000 \
>   -e TASK_DB=/data/tasks.db \
>   -v $(PWD)/.data:/data \
>   $(IMAGE)
# ----- systemd helpers (user services) -----
.PHONY: systemd-reload systemd-start systemd-stop systemd-status systemd-logs \
        worker-start worker-stop worker-status worker-logs

systemd-reload:
	@systemctl --user daemon-reload

systemd-start:
	@systemctl --user enable --now velu-server.service
	@systemctl --user status --no-pager velu-server.service

systemd-stop:
	@systemctl --user disable --now velu-server.service || true

systemd-status:
	@systemctl --user status --no-pager velu-server.service

systemd-logs:
	@journalctl --user -u velu-server.service -n 120 --no-pager

# N defaults to 0 (run forever). Use: make worker-start N=25
N ?= 0
worker-start:
	@systemctl --user enable --now velu-worker@$(N).service
	@systemctl --user status --no-pager velu-worker@$(N).service

worker-stop:
	@systemctl --user disable --now velu-worker@$(N).service || true

worker-status:
	@systemctl --user status --no-pager velu-worker@$(N).service

worker-logs:
	@journalctl --user -u velu-worker@$(N).service -n 120 --no-pager
.PHONY: git-feature git-fix git-chore git-release
git-feature:
	@env VELU_REPO_PATH=$(PWD) python - <<'PY'
from agents.git_agent.agent import GitIntegrationAgent
a=GitIntegrationAgent()
print(a.feature_commit(scope="${SCOPE:-misc}", summary="${MSG:-feature}", body=""))
PY

git-fix:
	@env VELU_REPO_PATH=$(PWD) python - <<'PY'
from agents.git_agent.agent import GitIntegrationAgent
a=GitIntegrationAgent()
print(a.fix_commit(scope="${SCOPE:-misc}", summary="${MSG:-fix}", body=""))
PY

git-chore:
	@env VELU_REPO_PATH=$(PWD) python - <<'PY'
from agents.git_agent.agent import GitIntegrationAgent
a=GitIntegrationAgent()
print(a.chore_commit(scope="${SCOPE:-repo}", summary="${MSG:-chore}", body=""))
PY

git-release:
	@env VELU_REPO_PATH=$(PWD) python - <<'PY'
from agents.git_agent.agent import GitIntegrationAgent
a=GitIntegrationAgent()
print(a.release(version="${VER:-0.1.0}", summary=""))
PY
