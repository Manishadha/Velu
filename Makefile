.PHONY: up down logs test release

up:
\tdocker compose up -d

down:
\tdocker compose down

logs:
\tdocker compose logs -f --tail=100

test:
\tpytest -q

# usage: make release TAG=v0.1.9
release:
\t@if [ -z "$(TAG)" ]; then echo "TAG required, e.g. make release TAG=v0.1.9"; exit 1; fi
\tgit tag -a "$(TAG)" -m "Release $(TAG)"
\tgit push origin "$(TAG)"
