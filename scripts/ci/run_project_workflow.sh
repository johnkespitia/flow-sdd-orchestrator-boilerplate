#!/usr/bin/env bash
set -euo pipefail

WORKFLOW_PATH="${1:?workflow path required}"
TARGET_REPOSITORY="${2:?workflow repository required}"
TARGET_REF="${3:?workflow ref required}"
HEAD_SHA="${4:?head sha required}"
INPUTS_JSON="${5:-{}}"

if ! command -v gh >/dev/null 2>&1; then
  echo "gh is required to dispatch project workflows." >&2
  exit 2
fi

if [[ -z "$WORKFLOW_PATH" ]]; then
  echo "workflow path is empty" >&2
  exit 2
fi

if [[ "$INPUTS_JSON" != "null" && "$INPUTS_JSON" != "" ]]; then
  mapfile -t EXTRA_INPUTS < <(
    python3 - <<'PY' "$INPUTS_JSON"
import json
import sys
payload = json.loads(sys.argv[1])
if not isinstance(payload, dict):
    raise SystemExit(0)
for key, value in payload.items():
    print(f"{key}={value}")
PY
  )
else
  EXTRA_INPUTS=()
fi

START_TS="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

CMD=(gh workflow run "$WORKFLOW_PATH" --repo "$TARGET_REPOSITORY" --ref "$TARGET_REF")
for item in "${EXTRA_INPUTS[@]}"; do
  CMD+=(-f "$item")
done
"${CMD[@]}"

RUN_ID=""
for _attempt in $(seq 1 30); do
  RUN_ID="$(gh run list \
    --repo "$TARGET_REPOSITORY" \
    --workflow "$WORKFLOW_PATH" \
    --json databaseId,event,headSha,createdAt \
    --limit 20 \
    --jq ".[] | select(.event == \"workflow_dispatch\" and .headSha == \"$HEAD_SHA\" and .createdAt >= \"$START_TS\") | .databaseId" \
    | head -n 1 || true)"
  if [[ -n "$RUN_ID" ]]; then
    break
  fi
  sleep 5
done

if [[ -z "$RUN_ID" ]]; then
  echo "Could not discover dispatched run for $WORKFLOW_PATH on $TARGET_REPOSITORY." >&2
  exit 1
fi

gh run watch "$RUN_ID" --repo "$TARGET_REPOSITORY" --exit-status
