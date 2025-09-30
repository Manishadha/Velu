#!/usr/bin/env bash
set -euo pipefail
. .venv/bin/activate || true
pip install safety cyclonedx-bom > /dev/null 2>&1 || true
safety check -r requirements.txt || true
cyclonedx-bom -r -o sbom.xml || true
echo "Audit complete (best-effort)."
