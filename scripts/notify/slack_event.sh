#!/usr/bin/env bash

set -euo pipefail

: "${FLOW_WORKSPACE_ROOT:?FLOW_WORKSPACE_ROOT is required}"

message="${FLOW_NOTIFY_MESSAGE:-}"
if [[ -z "${message}" ]]; then
  exit 0
fi

if [[ -z "${SOFTOS_SLACK_WEBHOOK_URL:-}" ]]; then
  exit 0
fi

FLOW_FEEDBACK_MESSAGE="${message}" \
FLOW_SLACK_RESPONSE_URL="" \
bash "${FLOW_WORKSPACE_ROOT}/scripts/providers/feedback/slack_webhook.sh" >/dev/null
