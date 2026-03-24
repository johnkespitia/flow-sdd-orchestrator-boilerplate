#!/usr/bin/env bash

set -euo pipefail

: "${FLOW_PROVIDER_ACTION:?FLOW_PROVIDER_ACTION is required}"
: "${FLOW_RELEASE_VERSION:?FLOW_RELEASE_VERSION is required}"
: "${FLOW_RELEASE_ENV:?FLOW_RELEASE_ENV is required}"

if [[ "${FLOW_PROVIDER_ACTION}" != "promote" ]]; then
  echo "Unsupported release action: ${FLOW_PROVIDER_ACTION}" >&2
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI is required for provider ftp-bridge." >&2
  exit 1
fi

: "${FLOW_DEPLOY_GITHUB_REPO:?FLOW_DEPLOY_GITHUB_REPO is required (owner/repo)}"
workflow="${FLOW_DEPLOY_GITHUB_WORKFLOW:-deploy.yml}"
ref="${FLOW_DEPLOY_GITHUB_REF:-main}"

gh workflow run "${workflow}" \
  --repo "${FLOW_DEPLOY_GITHUB_REPO}" \
  --ref "${ref}" \
  -f version="${FLOW_RELEASE_VERSION}" \
  -f environment="${FLOW_RELEASE_ENV}"
