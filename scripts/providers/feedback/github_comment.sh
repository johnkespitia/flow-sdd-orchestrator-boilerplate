#!/usr/bin/env bash

set -euo pipefail

: "${SOFTOS_GITHUB_TOKEN:?SOFTOS_GITHUB_TOKEN is required}"
: "${FLOW_GITHUB_COMMENTS_URL:?FLOW_GITHUB_COMMENTS_URL is required}"
: "${FLOW_FEEDBACK_MESSAGE:?FLOW_FEEDBACK_MESSAGE is required}"

payload="$(python3 - <<'PY'
import json
import os

print(json.dumps({"body": os.environ["FLOW_FEEDBACK_MESSAGE"]}, ensure_ascii=True))
PY
)"

curl -fsSL -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer ${SOFTOS_GITHUB_TOKEN}" \
  -H "Content-Type: application/json" \
  --data "${payload}" \
  "${FLOW_GITHUB_COMMENTS_URL}" >/dev/null

echo "github-ok"
