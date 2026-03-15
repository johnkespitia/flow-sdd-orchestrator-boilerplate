#!/usr/bin/env bash

set -euo pipefail

: "${FLOW_WORKSPACE_ROOT:?FLOW_WORKSPACE_ROOT is required}"

log_dir="${FLOW_WORKSPACE_ROOT}/gateway/data"
log_file="${log_dir}/outbox.log"
mkdir -p "${log_dir}"

timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
message="${FLOW_FEEDBACK_MESSAGE:-No feedback message provided.}"
provider="${FLOW_PROVIDER_NAME:-local-log}"
status="${FLOW_FEEDBACK_STATUS:-unknown}"
task_id="${FLOW_FEEDBACK_TASK_ID:-unknown}"
target="${FLOW_FEEDBACK_TARGET_KIND:-none}"

{
  printf '[%s] provider=%s status=%s task=%s target=%s\n' "${timestamp}" "${provider}" "${status}" "${task_id}" "${target}"
  printf '%s\n' "${message}"
  printf '\n'
} >> "${log_file}"

printf 'logged:%s\n' "${log_file}"
