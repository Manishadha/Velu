#!/usr/bin/env bash
set -euo pipefail
. .venv/bin/activate || true

# 1) vulnerability scan (new Safety v3+)
python -m pip install --upgrade safety cyclonedx-bom >/dev/null 2>&1 || true
safety scan -r requirements.txt || true

# 2) SBOM (CycloneDX)
cyclonedx-bom -r -o sbom.xml || true

echo "Audit complete. SBOM -> sbom.xml"
