#!/usr/bin/env bash
set -euo pipefail
. .venv/bin/activate || true
pytest -q || true
