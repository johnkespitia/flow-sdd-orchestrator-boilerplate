#!/usr/bin/env bash

set -euo pipefail

: "${SOFTOS_JIRA_BASE_URL:?SOFTOS_JIRA_BASE_URL is required}"
: "${SOFTOS_JIRA_USER_EMAIL:?SOFTOS_JIRA_USER_EMAIL is required}"
: "${SOFTOS_JIRA_API_TOKEN:?SOFTOS_JIRA_API_TOKEN is required}"
: "${FLOW_JIRA_ISSUE_KEY:?FLOW_JIRA_ISSUE_KEY is required}"
: "${FLOW_FEEDBACK_MESSAGE:?FLOW_FEEDBACK_MESSAGE is required}"

jira_url="${SOFTOS_JIRA_BASE_URL%/}/rest/api/3/issue/${FLOW_JIRA_ISSUE_KEY}/comment"

payload="$(python3 - <<'PY'
import json
import os

body = {
    "body": {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": os.environ["FLOW_FEEDBACK_MESSAGE"],
                    }
                ],
            }
        ],
    }
}
print(json.dumps(body, ensure_ascii=True))
PY
)"

curl -fsSL -X POST \
  -u "${SOFTOS_JIRA_USER_EMAIL}:${SOFTOS_JIRA_API_TOKEN}" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  --data "${payload}" \
  "${jira_url}" >/dev/null

echo "jira-ok"
