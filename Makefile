.PHONY: up down logs rebuild fmt lint

up:
\tdocker compose up -d

down:
\tdocker compose down

logs:
\tdocker compose logs -f --tail=200

rebuild:
\tdocker compose build --no-cache
\tdocker compose up -d --force-recreate

fmt:
\tpython -m black services || true

lint:
\tpython -m ruff services || true
