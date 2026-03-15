#!/usr/bin/env bash

set -euo pipefail

: "${FLOW_SECRET_REF:?FLOW_SECRET_REF is required}"

case "${FLOW_SECRET_REF}" in
  op:*)
    op read "${FLOW_SECRET_REF#op:}"
    ;;
  *)
    echo "Unsupported 1Password secret reference: ${FLOW_SECRET_REF}" >&2
    exit 1
    ;;
esac
