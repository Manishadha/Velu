#!/usr/bin/env bash
set -euo pipefail
. .venv/bin/activate || true
ruff check . || true
ruff format --check . || true
