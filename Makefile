.PHONY: setup run test lint audit api api-8001 all-up all-down api-up api-down

setup: ; bash scripts/setup.sh
run: ; bash scripts/run.sh
test: ; bash scripts/test.sh
lint: ; bash scripts/lint.sh
audit: ; bash scripts/audit.sh

api: ; uvicorn services.app_server.main:app --host 0.0.0.0 --port 8000 --reload
api-8001: ; uvicorn services.app_server.main:app --host 0.0.0.0 --port 8001 --reload

all-up: ; docker compose up --build
all-down: ; docker compose down
api-up: ; docker compose up --build api
api-down: ; docker compose stop api
