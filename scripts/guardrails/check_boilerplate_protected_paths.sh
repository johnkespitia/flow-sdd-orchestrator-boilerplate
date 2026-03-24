#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-$(pwd)}"
cd "$ROOT_DIR"

if [[ "${ALLOW_BOILERPLATE_CORE_CHANGES:-0}" == "1" ]]; then
  echo "Boilerplate guardrail bypassed by ALLOW_BOILERPLATE_CORE_CHANGES=1"
  exit 0
fi

if [[ "${ENFORCE_BOILERPLATE_GUARDRAILS:-0}" != "1" ]] && [[ -f workspace.config.json ]]; then
  ROOT_REPO="$(python3 - <<'PY'
import json
from pathlib import Path
try:
    payload = json.loads(Path("workspace.config.json").read_text(encoding="utf-8"))
except Exception:
    payload = {}
print(str(payload.get("project", {}).get("root_repo", "")).strip())
PY
)"
  if [[ "$ROOT_REPO" == "sdd-workspace-boilerplate" ]]; then
    echo "Boilerplate guardrail skipped in source workspace (set ENFORCE_BOILERPLATE_GUARDRAILS=1 to enforce)."
    exit 0
  fi
fi

MODE="staged"
BASE_SHA=""
HEAD_SHA=""

usage() {
  cat <<USAGE
Usage:
  scripts/guardrails/check_boilerplate_protected_paths.sh --staged
  scripts/guardrails/check_boilerplate_protected_paths.sh --base <sha> --head <sha>

Env override:
  ALLOW_BOILERPLATE_CORE_CHANGES=1  Bypass this guardrail intentionally.
  ENFORCE_BOILERPLATE_GUARDRAILS=1  Enforce even in source workspace.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --staged)
      MODE="staged"
      shift
      ;;
    --base)
      MODE="range"
      BASE_SHA="${2:-}"
      shift 2
      ;;
    --head)
      MODE="range"
      HEAD_SHA="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "$MODE" == "range" ]] && { [[ -z "$BASE_SHA" ]] || [[ -z "$HEAD_SHA" ]]; }; then
  echo "--base and --head are required together." >&2
  usage >&2
  exit 2
fi

if [[ ! -f scripts/guardrails/boilerplate_protected_paths.txt ]]; then
  echo "Missing scripts/guardrails/boilerplate_protected_paths.txt" >&2
  exit 2
fi

mapfile -t CHANGED_FILES < <(
  if [[ "$MODE" == "staged" ]]; then
    git diff --cached --name-only --diff-filter=ACMR
  else
    git diff --name-only --diff-filter=ACMR "$BASE_SHA" "$HEAD_SHA"
  fi
)

if [[ ${#CHANGED_FILES[@]} -eq 0 ]]; then
  exit 0
fi

mapfile -t PATTERNS < <(
  sed -e 's/[[:space:]]*$//' scripts/guardrails/boilerplate_protected_paths.txt \
    | rg -v '^\s*(#|$)'
)

if [[ ${#PATTERNS[@]} -eq 0 ]]; then
  exit 0
fi

VIOLATIONS=()
for file in "${CHANGED_FILES[@]}"; do
  for pattern in "${PATTERNS[@]}"; do
    if [[ "$file" == $pattern ]]; then
      VIOLATIONS+=("$file")
      break
    fi
  done
done

if [[ ${#VIOLATIONS[@]} -eq 0 ]]; then
  exit 0
fi

printf '%s\n' "Guardrail: detected changes in boilerplate-protected files:" >&2
printf ' - %s\n' "${VIOLATIONS[@]}" >&2
cat >&2 <<'EOM'

If this change is intentional (boilerplate maintenance), rerun with:
  ALLOW_BOILERPLATE_CORE_CHANGES=1

Otherwise, move implementation changes to project/spec paths (for example `projects/**`, `specs/features/**`).
EOM

exit 1
