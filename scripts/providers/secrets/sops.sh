#!/usr/bin/env bash

set -euo pipefail

: "${FLOW_SECRET_REF:?FLOW_SECRET_REF is required}"

case "${FLOW_SECRET_REF}" in
  sops:*)
    payload="${FLOW_SECRET_REF#sops:}"
    file_path="${payload%%#*}"
    extract_expr="${payload#*#}"
    if [[ "${file_path}" == "${extract_expr}" ]]; then
      echo "SOPS refs must use the form sops:path/to/file#extract-expression" >&2
      exit 1
    fi
    sops --decrypt --extract "${extract_expr}" "${file_path}"
    ;;
  *)
    echo "Unsupported SOPS secret reference: ${FLOW_SECRET_REF}" >&2
    exit 1
    ;;
esac
