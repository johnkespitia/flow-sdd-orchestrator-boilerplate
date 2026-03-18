#!/usr/bin/env bash

set -euo pipefail

: "${FLOW_WORKSPACE_ROOT:?FLOW_WORKSPACE_ROOT is required}"
: "${FLOW_RELEASE_VERSION:?FLOW_RELEASE_VERSION is required}"
: "${FLOW_RELEASE_ENV:?FLOW_RELEASE_ENV is required}"
: "${FLOW_RELEASE_MANIFEST:?FLOW_RELEASE_MANIFEST is required}"

notify_script="${FLOW_WORKSPACE_ROOT}/scripts/notify/slack_event.sh"
notify_slack() {
  local message="$1"
  if [[ ! -f "${notify_script}" ]]; then
    return 0
  fi
  FLOW_NOTIFY_MESSAGE="${message}" bash "${notify_script}" || true
}

feature_list="unknown"
completed=0
cleanup() {
  local exit_code=$?
  if [[ ${exit_code} -ne 0 && ${completed} -eq 0 ]]; then
    notify_slack "$(cat <<EOF
SoftOS delivery failed
Stage: release promote
Version: ${FLOW_RELEASE_VERSION}
Environment: ${FLOW_RELEASE_ENV}
Features: ${feature_list}
Status: failed
EOF
)"
  fi
}
trap cleanup EXIT

if ! parsed_feature_list="$(python3 - <<'PY'
import json
import os
from pathlib import Path

manifest = json.loads(Path(os.environ["FLOW_RELEASE_MANIFEST"]).read_text(encoding="utf-8"))
features = manifest.get("features", [])
slugs = [str(item.get("slug", "")).strip() for item in features if isinstance(item, dict)]
slugs = [slug for slug in slugs if slug]
print(", ".join(slugs) or "unknown")
PY
)"; then
  exit 1
fi
feature_list="${parsed_feature_list:-unknown}"

echo "Promoting release ${FLOW_RELEASE_VERSION} to ${FLOW_RELEASE_ENV}"
echo "Using manifest ${FLOW_RELEASE_MANIFEST}"

completed=1
