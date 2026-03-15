#!/usr/bin/env bash

set -euo pipefail

: "${FLOW_INFRA_ENV:?FLOW_INFRA_ENV is required}"
: "${FLOW_INFRA_PLAN:?FLOW_INFRA_PLAN is required}"

echo "Applying infra plan ${FLOW_INFRA_PLAN} to ${FLOW_INFRA_ENV}"
