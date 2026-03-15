#!/usr/bin/env bash

set -euo pipefail

: "${FLOW_PROVIDER_ACTION:?FLOW_PROVIDER_ACTION is required}"
: "${FLOW_WORKSPACE_ROOT:?FLOW_WORKSPACE_ROOT is required}"

case "${FLOW_PROVIDER_ACTION}" in
  plan)
    script="${FLOW_WORKSPACE_ROOT}/scripts/infra/plan.sh"
    ;;
  apply)
    script="${FLOW_WORKSPACE_ROOT}/scripts/infra/apply.sh"
    ;;
  *)
    echo "Unsupported infra action: ${FLOW_PROVIDER_ACTION}" >&2
    exit 1
    ;;
esac

if [[ ! -f "${script}" ]]; then
  echo "Missing infra hook: ${script}" >&2
  exit 1
fi

exec bash "${script}"
