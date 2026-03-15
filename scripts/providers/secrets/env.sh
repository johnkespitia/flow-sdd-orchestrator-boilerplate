#!/usr/bin/env bash

set -euo pipefail

: "${FLOW_SECRET_REF:?FLOW_SECRET_REF is required}"

case "${FLOW_SECRET_REF}" in
  env:*)
    var_name="${FLOW_SECRET_REF#env:}"
    printenv "${var_name}" || true
    ;;
  literal:*)
    printf '%s' "${FLOW_SECRET_REF#literal:}"
    ;;
  *)
    echo "Unsupported env secret reference: ${FLOW_SECRET_REF}" >&2
    exit 1
    ;;
esac
