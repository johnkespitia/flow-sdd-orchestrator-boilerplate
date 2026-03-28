#!/usr/bin/env bash
# Arranque estándar del gateway para entorno compartido (o local con mismas variables).
# Respeta FLOW_WORKSPACE_ROOT y DB; no sustituye secret manager ni Postgres (ver runbook).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export FLOW_WORKSPACE_ROOT="${FLOW_WORKSPACE_ROOT:-$ROOT}"
PY="${SOFTOS_GATEWAY_PYTHON:-python3}"
HOST="${SOFTOS_GATEWAY_HOST:-0.0.0.0}"
PORT="${SOFTOS_GATEWAY_PORT:-8010}"
cd "${ROOT}/gateway"
exec "${PY}" -m uvicorn app.main:app --host "${HOST}" --port "${PORT}"
