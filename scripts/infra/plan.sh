#!/usr/bin/env bash

set -euo pipefail

: "${FLOW_WORKSPACE_ROOT:?FLOW_WORKSPACE_ROOT is required}"
: "${FLOW_INFRA_ENV:?FLOW_INFRA_ENV is required}"
: "${FLOW_INFRA_SPEC:?FLOW_INFRA_SPEC is required}"

notify_script="${FLOW_WORKSPACE_ROOT}/scripts/notify/slack_event.sh"
notify_slack() {
  local message="$1"
  if [[ ! -f "${notify_script}" ]]; then
    return 0
  fi
  FLOW_NOTIFY_MESSAGE="${message}" bash "${notify_script}" || true
}

completed=0
cleanup() {
  local exit_code=$?
  if [[ ${exit_code} -ne 0 && ${completed} -eq 0 ]]; then
    notify_slack "$(cat <<EOF
SoftOS delivery failed
Stage: infra plan
Spec: ${FLOW_INFRA_SPEC}
Environment: ${FLOW_INFRA_ENV}
Status: failed
EOF
)"
  fi
}
trap cleanup EXIT

echo "Planning infra for ${FLOW_INFRA_SPEC} in ${FLOW_INFRA_ENV}"

completed=1
