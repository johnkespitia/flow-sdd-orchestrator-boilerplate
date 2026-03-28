#!/usr/bin/env bash
# Smoke reproducible para gateway desplegado (central o local). No modifica estado.
set -euo pipefail
BASE="${SOFTOS_GATEWAY_URL:-http://127.0.0.1:8010}"
BASE="${BASE%/}"
curl -sfS "${BASE}/healthz" >/dev/null
echo "gateway smoke OK: ${BASE}/healthz"
