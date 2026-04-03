#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "$#" -eq 0 ]]; then
  echo "usage: scripts/workspace_exec.sh <command> [args...]" >&2
  exit 2
fi

exec python3 "$ROOT_DIR/flow" workspace exec -- "$@"
