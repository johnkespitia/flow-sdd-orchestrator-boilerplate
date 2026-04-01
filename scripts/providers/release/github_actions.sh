#!/usr/bin/env bash

set -euo pipefail

: "${FLOW_PROVIDER_ACTION:?FLOW_PROVIDER_ACTION is required}"
: "${FLOW_RELEASE_VERSION:?FLOW_RELEASE_VERSION is required}"
: "${FLOW_RELEASE_ENV:?FLOW_RELEASE_ENV is required}"

workflow="${FLOW_DEPLOY_GITHUB_WORKFLOW:-${FLOW_GITHUB_RELEASE_WORKFLOW:-release-promote.yml}}"
target_repo="${FLOW_DEPLOY_GITHUB_REPO:-}"
target_ref="${FLOW_DEPLOY_GITHUB_REF:-main}"
source_ref="${FLOW_DEPLOY_SOURCE_REF:-}"
requested_by="${FLOW_DEPLOY_REQUESTED_BY:-${FLOW_RELEASE_APPROVER:-}}"
run_migrations="${FLOW_DEPLOY_RUN_MIGRATIONS:-}"

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI is required for provider github-actions." >&2
  exit 1
fi

if [[ "${FLOW_PROVIDER_ACTION}" != "promote" ]]; then
  echo "Unsupported release action: ${FLOW_PROVIDER_ACTION}" >&2
  exit 1
fi

args=(
  workflow
  run
  "${workflow}"
  -f
  "environment=${FLOW_RELEASE_ENV}"
  -f
  "version=${FLOW_RELEASE_VERSION}"
)

if [[ -n "${target_repo}" ]]; then
  args+=(--repo "${target_repo}")
fi

if [[ -n "${target_ref}" ]]; then
  args+=(--ref "${target_ref}")
fi

if [[ -n "${source_ref}" ]]; then
  args+=(-f "source_ref=${source_ref}")
fi

if [[ -n "${requested_by}" ]]; then
  args+=(-f "requested_by=${requested_by}")
fi

if [[ -n "${run_migrations}" ]]; then
  args+=(-f "run_migrations=${run_migrations}")
fi

gh "${args[@]}"
