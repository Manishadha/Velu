.PHONY: setup run test lint audit
setup: ; bash scripts/setup.sh
run: ; bash scripts/run.sh
test: ; bash scripts/test.sh
lint: ; bash scripts/lint.sh
audit: ; bash scripts/audit.sh
