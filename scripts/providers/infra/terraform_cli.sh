#!/usr/bin/env bash

set -euo pipefail

: "${FLOW_PROVIDER_ACTION:?FLOW_PROVIDER_ACTION is required}"

if ! command -v terraform >/dev/null 2>&1; then
  echo "Terraform CLI is required for provider terraform-cli." >&2
  exit 1
fi

workdir="${FLOW_TERRAFORM_WORKDIR:-.}"

case "${FLOW_PROVIDER_ACTION}" in
  plan)
    terraform -chdir="${workdir}" plan
    ;;
  apply)
    terraform -chdir="${workdir}" apply -auto-approve
    ;;
  *)
    echo "Unsupported infra action: ${FLOW_PROVIDER_ACTION}" >&2
    exit 1
    ;;
esac
