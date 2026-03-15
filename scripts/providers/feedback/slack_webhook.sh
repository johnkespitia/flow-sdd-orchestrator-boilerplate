#!/usr/bin/env bash

set -euo pipefail

target_url="${FLOW_SLACK_RESPONSE_URL:-${SOFTOS_SLACK_WEBHOOK_URL:-}}"
if [[ -z "${target_url}" ]]; then
  echo "Missing Slack response/webhook URL." >&2
  exit 1
fi

: "${FLOW_FEEDBACK_MESSAGE:?FLOW_FEEDBACK_MESSAGE is required}"

payload="$(python3 - <<'PY'
import json
import os

print(json.dumps({"text": os.environ["FLOW_FEEDBACK_MESSAGE"]}, ensure_ascii=True))
PY
)"

curl -fsSL -X POST \
  -H "Content-Type: application/json" \
  --data "${payload}" \
  "${target_url}" >/dev/null

echo "slack-ok"
