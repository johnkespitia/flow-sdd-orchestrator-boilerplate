#!/usr/bin/env bash

set -euo pipefail

: "${FLOW_PROVIDER_ACTION:?FLOW_PROVIDER_ACTION is required}"
: "${FLOW_RELEASE_VERSION:?FLOW_RELEASE_VERSION is required}"
: "${FLOW_RELEASE_ENV:?FLOW_RELEASE_ENV is required}"

workflow="${FLOW_GITHUB_RELEASE_WORKFLOW:-release-promote.yml}"

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI is required for provider github-actions." >&2
  exit 1
fi

if [[ "${FLOW_PROVIDER_ACTION}" != "promote" ]]; then
  echo "Unsupported release action: ${FLOW_PROVIDER_ACTION}" >&2
  exit 1
fi

gh workflow run "${workflow}" \
  -f version="${FLOW_RELEASE_VERSION}" \
  -f environment="${FLOW_RELEASE_ENV}"
