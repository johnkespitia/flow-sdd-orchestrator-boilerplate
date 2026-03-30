#!/usr/bin/env bash

set -euo pipefail

: "${FLOW_DEPLOY_ENV:?FLOW_DEPLOY_ENV is required}"
: "${FLOW_DEPLOY_TARGET_PATH:?FLOW_DEPLOY_TARGET_PATH is required}"

deploy_env="${FLOW_DEPLOY_ENV}"
target_path="${FLOW_DEPLOY_TARGET_PATH}"
base_prefix="${FLOW_DEPLOY_BASE_PREFIX:-/}"
staging_path="${FLOW_DEPLOY_STAGING_PATH:-}"
production_path="${FLOW_DEPLOY_PRODUCTION_PATH:-}"
staging_suffix="${FLOW_DEPLOY_STAGING_SUFFIX:-}"
production_suffix="${FLOW_DEPLOY_PRODUCTION_SUFFIX:-}"
staging_forbidden_fragment="${FLOW_DEPLOY_STAGING_FORBIDDEN_FRAGMENT:-/public_html/}"
production_forbidden_fragment="${FLOW_DEPLOY_PRODUCTION_FORBIDDEN_FRAGMENT:-}"

if [[ "${target_path}" != /* ]]; then
  echo "Target path must be absolute: ${target_path}" >&2
  exit 1
fi

if [[ "${target_path}" != "${base_prefix}"* ]]; then
  echo "Target path must start with ${base_prefix}: ${target_path}" >&2
  exit 1
fi

case "${deploy_env}" in
  staging)
    if [[ -n "${staging_forbidden_fragment}" && "${target_path}" == *"${staging_forbidden_fragment}"* ]]; then
      echo "Staging path cannot include ${staging_forbidden_fragment}: ${target_path}" >&2
      exit 1
    fi
    if [[ -n "${staging_suffix}" && "${target_path}" != *"${staging_suffix}" ]]; then
      echo "Staging path must end with ${staging_suffix}: ${target_path}" >&2
      exit 1
    fi
    ;;
  production)
    if [[ -n "${production_forbidden_fragment}" && "${target_path}" == *"${production_forbidden_fragment}"* ]]; then
      echo "Production path cannot include ${production_forbidden_fragment}: ${target_path}" >&2
      exit 1
    fi
    if [[ -n "${production_suffix}" && "${target_path}" != *"${production_suffix}" ]]; then
      echo "Production path must end with ${production_suffix}: ${target_path}" >&2
      exit 1
    fi
    ;;
  *)
    echo "Unsupported environment: ${deploy_env}" >&2
    exit 1
    ;;
esac

inode_of() {
  local path="$1"
  if stat -c '%d:%i' "${path}" >/dev/null 2>&1; then
    stat -c '%d:%i' "${path}"
  else
    stat -f '%d:%i' "${path}"
  fi
}

check_local_symlink_guardrails() {
  local path="$1"
  local label="$2"
  if [[ ! -e "${path}" ]]; then
    return 0
  fi

  if [[ -L "${path}/.env" ]]; then
    echo "${label} .env cannot be a symlink: ${path}/.env" >&2
    exit 1
  fi

  if [[ -L "${path}/storage" ]]; then
    echo "${label} storage cannot be a symlink: ${path}/storage" >&2
    exit 1
  fi
}

if [[ -n "${staging_path}" && -n "${production_path}" ]]; then
  if [[ "${deploy_env}" == "staging" ]]; then
    counterpart_path="${production_path}"
  else
    counterpart_path="${staging_path}"
  fi

  check_local_symlink_guardrails "${target_path}" "target"
  check_local_symlink_guardrails "${counterpart_path}" "counterpart"

  if [[ -f "${staging_path}/.env" && -f "${production_path}/.env" ]]; then
    staging_env_inode="$(inode_of "${staging_path}/.env")"
    production_env_inode="$(inode_of "${production_path}/.env")"
    if [[ "${staging_env_inode}" == "${production_env_inode}" ]]; then
      echo "staging and production .env cannot point to the same file inode" >&2
      exit 1
    fi
  fi

  if [[ -d "${staging_path}/storage" && -d "${production_path}/storage" ]]; then
    staging_storage_inode="$(inode_of "${staging_path}/storage")"
    production_storage_inode="$(inode_of "${production_path}/storage")"
    if [[ "${staging_storage_inode}" == "${production_storage_inode}" ]]; then
      echo "staging and production storage cannot point to the same directory inode" >&2
      exit 1
    fi
  fi
fi

echo "Path/isolation guardrails passed for ${deploy_env} (${target_path})"
