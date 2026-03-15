#!/usr/bin/env bash

set -euo pipefail

: "${FLOW_RELEASE_VERSION:?FLOW_RELEASE_VERSION is required}"
: "${FLOW_RELEASE_ENV:?FLOW_RELEASE_ENV is required}"
: "${FLOW_RELEASE_MANIFEST:?FLOW_RELEASE_MANIFEST is required}"

echo "Promoting release ${FLOW_RELEASE_VERSION} to ${FLOW_RELEASE_ENV}"
echo "Using manifest ${FLOW_RELEASE_MANIFEST}"
