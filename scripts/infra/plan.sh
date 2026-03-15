#!/usr/bin/env bash

set -euo pipefail

: "${FLOW_INFRA_ENV:?FLOW_INFRA_ENV is required}"
: "${FLOW_INFRA_SPEC:?FLOW_INFRA_SPEC is required}"

echo "Planning infra for ${FLOW_INFRA_SPEC} in ${FLOW_INFRA_ENV}"
