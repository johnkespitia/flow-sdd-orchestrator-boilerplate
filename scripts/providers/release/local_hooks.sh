#!/usr/bin/env bash

set -euo pipefail

: "${FLOW_PROVIDER_ACTION:?FLOW_PROVIDER_ACTION is required}"
: "${FLOW_WORKSPACE_ROOT:?FLOW_WORKSPACE_ROOT is required}"

if [[ "${FLOW_PROVIDER_ACTION}" != "promote" ]]; then
  echo "Unsupported release action: ${FLOW_PROVIDER_ACTION}" >&2
  exit 1
fi

: "${FLOW_RELEASE_ENV:?FLOW_RELEASE_ENV is required}"

specific="${FLOW_WORKSPACE_ROOT}/scripts/release/promote_${FLOW_RELEASE_ENV}.sh"
generic="${FLOW_WORKSPACE_ROOT}/scripts/release/promote.sh"

if [[ -f "${specific}" ]]; then
  exec bash "${specific}"
fi

if [[ -f "${generic}" ]]; then
  exec bash "${generic}"
fi

echo "No release hook found for ${FLOW_RELEASE_ENV}; nothing to execute."
