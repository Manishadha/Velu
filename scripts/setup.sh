#!/usr/bin/env bash
set -euo pipefail
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
if command -v pre-commit >/dev/null 2>&1; then pre-commit install; fi
echo "Setup complete. Activate: source .venv/bin/activate"
