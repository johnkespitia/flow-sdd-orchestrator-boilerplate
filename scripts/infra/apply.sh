#!/usr/bin/env bash

set -euo pipefail

: "${FLOW_WORKSPACE_ROOT:?FLOW_WORKSPACE_ROOT is required}"
: "${FLOW_INFRA_ENV:?FLOW_INFRA_ENV is required}"
: "${FLOW_INFRA_PLAN:?FLOW_INFRA_PLAN is required}"

notify_script="${FLOW_WORKSPACE_ROOT}/scripts/notify/slack_event.sh"
notify_slack() {
  local message="$1"
  if [[ ! -f "${notify_script}" ]]; then
    return 0
  fi
  FLOW_NOTIFY_MESSAGE="${message}" bash "${notify_script}" || true
}

feature_slug="unknown"
completed=0
cleanup() {
  local exit_code=$?
  if [[ ${exit_code} -ne 0 && ${completed} -eq 0 ]]; then
    notify_slack "$(cat <<EOF
SoftOS delivery failed
Stage: infra apply
Feature: ${feature_slug}
Environment: ${FLOW_INFRA_ENV}
Status: failed
EOF
)"
  fi
}
trap cleanup EXIT

if ! parsed_feature_slug="$(python3 - <<'PY'
import json
import os
from pathlib import Path

plan = json.loads(Path(os.environ["FLOW_INFRA_PLAN"]).read_text(encoding="utf-8"))
print(str(plan.get("feature", "unknown")).strip() or "unknown")
PY
)"; then
  exit 1
fi
feature_slug="${parsed_feature_slug:-unknown}"

echo "Applying infra plan ${FLOW_INFRA_PLAN} to ${FLOW_INFRA_ENV}"

notify_slack "$(cat <<EOF
SoftOS change ready
Feature: ${feature_slug}
Environment: ${FLOW_INFRA_ENV}
Stage: infra apply
Status: ready
EOF
)"

completed=1
