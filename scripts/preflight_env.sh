#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

AUTO_UP=1
BUILD_IMAGES=0
CHECK_SPEC_CI=0
RUN_MIGRATIONS=0
PREFLIGHT_CONFIG="workspace.preflight.json"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-auto-up)
      AUTO_UP=0
      shift
      ;;
    --build)
      BUILD_IMAGES=1
      shift
      ;;
    --check-spec-ci)
      CHECK_SPEC_CI=1
      shift
      ;;
    --run-migrations)
      RUN_MIGRATIONS=1
      shift
      ;;
    --config)
      PREFLIGHT_CONFIG="${2:-}"
      if [[ -z "$PREFLIGHT_CONFIG" ]]; then
        echo "Missing value for --config" >&2
        exit 2
      fi
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Usage: scripts/preflight_env.sh [--no-auto-up] [--build] [--check-spec-ci] [--run-migrations] [--config <path>]" >&2
      exit 2
      ;;
  esac
done

export PREFLIGHT_CONFIG

FAILURES=0
WARNINGS=0

pass() { echo "[PASS] $*"; }
warn() { echo "[WARN] $*"; WARNINGS=$((WARNINGS + 1)); }
fail() { echo "[FAIL] $*"; FAILURES=$((FAILURES + 1)); }

run_check() {
  local label="$1"
  shift
  if "$@"; then
    pass "$label"
  else
    fail "$label"
  fi
}

echo "== SoftOS Environment Preflight =="
echo "Workspace: $ROOT_DIR"

run_check "flow doctor" python3 ./flow doctor >/dev/null
run_check "flow stack doctor" python3 ./flow stack doctor >/dev/null
run_check "flow workflow doctor" python3 ./flow workflow doctor --json >/dev/null
run_check "flow skills doctor" python3 ./flow skills doctor >/dev/null
run_check "flow providers doctor" python3 ./flow providers doctor >/dev/null
run_check "flow submodule doctor" python3 ./flow submodule doctor --json >/dev/null

echo "== Compose contract checks =="
if python3 - <<'PY'
from __future__ import annotations

import json
from pathlib import Path

import yaml

root = Path(".").resolve()
workspace_config = json.loads((root / "workspace.config.json").read_text(encoding="utf-8"))
compose_path = root / ".devcontainer" / "docker-compose.yml"
compose_payload = yaml.safe_load(compose_path.read_text(encoding="utf-8")) or {}
services = compose_payload.get("services", {}) if isinstance(compose_payload, dict) else {}

errors: list[str] = []
warnings: list[str] = []

repos = workspace_config.get("repos", {})
for repo_name, repo_cfg in repos.items():
    if not isinstance(repo_cfg, dict):
        continue
    if str(repo_cfg.get("kind", "")).strip() != "implementation":
        continue
    service_name = str(repo_cfg.get("compose_service", "")).strip()
    if not service_name:
        warnings.append(f"{repo_name}: no compose_service declared.")
        continue
    service = services.get(service_name)
    if not isinstance(service, dict):
        errors.append(f"{repo_name}: compose_service `{service_name}` not found in docker-compose.")
        continue

    command = service.get("command")
    command_text = ""
    if isinstance(command, list):
        command_text = " ".join(str(part) for part in command).strip().lower()
    elif isinstance(command, str):
        command_text = command.strip().lower()
    if "sleep infinity" in command_text:
        errors.append(f"{repo_name}: service `{service_name}` uses `sleep infinity` (app not persistent).")

    ports = service.get("ports")
    port_count = len(ports) if isinstance(ports, list) else 0
    runtime = str(repo_cfg.get("runtime", "")).strip().lower()
    serve_like = any(
        token in command_text
        for token in ("serve", "uvicorn", "npm start", "npm run dev", "php -s", "artisan")
    )
    if runtime in {"node", "php", "python"} and serve_like and port_count == 0:
        errors.append(
            f"{repo_name}: service `{service_name}` appears to run an app but exposes no host ports."
        )
    elif runtime in {"node", "php", "python"} and port_count == 0:
        warnings.append(
            f"{repo_name}: service `{service_name}` has no host port mapping; verify if intentional."
        )

for line in warnings:
    print(f"WARN: {line}")
for line in errors:
    print(f"ERROR: {line}")

if errors:
    raise SystemExit(1)
PY
then
  pass "compose service contract (commands/ports/env)"
else
  fail "compose service contract (commands/ports/env)"
fi

echo "== Cross-repo readiness policy checks =="
if PREFLIGHT_CONFIG="$PREFLIGHT_CONFIG" python3 - <<'PY'
from __future__ import annotations

import json
import re
from pathlib import Path
import os

root = Path(".").resolve()
workspace_config = json.loads((root / "workspace.config.json").read_text(encoding="utf-8"))
repos = workspace_config.get("repos", {})
config_path = root / os.environ.get("PREFLIGHT_CONFIG", "workspace.preflight.json")
preflight_cfg = {}
if config_path.exists():
    preflight_cfg = json.loads(config_path.read_text(encoding="utf-8"))

errors: list[str] = []
warnings: list[str] = []

implementation_repos: list[tuple[str, dict]] = [
    (name, cfg) for name, cfg in repos.items()
    if isinstance(cfg, dict) and str(cfg.get("kind", "")).strip() == "implementation"
]

contracts_dir = root / "contracts"
openapi_candidates = []
if contracts_dir.exists():
    for pattern in ("**/*openapi*.yml", "**/*openapi*.yaml", "**/*openapi*.json", "**/*swagger*.yml", "**/*swagger*.yaml", "**/*swagger*.json"):
        openapi_candidates.extend(contracts_dir.glob(pattern))
openapi_candidates = sorted({path.resolve() for path in openapi_candidates})

contracts_cfg = preflight_cfg.get("contracts", {}) if isinstance(preflight_cfg, dict) else {}
require_contracts_for_multi_repo = bool(contracts_cfg.get("required_for_multi_repo", True))
if require_contracts_for_multi_repo and len(implementation_repos) >= 2 and not openapi_candidates:
    errors.append(
        "No OpenAPI/Swagger contract found under `contracts/` for a multi-repo setup. Add an API contract to prevent interface drift."
    )

repo_overrides = preflight_cfg.get("repos", {}) if isinstance(preflight_cfg, dict) else {}
for repo_name, repo_cfg in implementation_repos:
    override = repo_overrides.get(repo_name, {}) if isinstance(repo_overrides, dict) else {}
    required_env_keys = override.get("required_env_keys", [])
    if not isinstance(required_env_keys, list) or not required_env_keys:
        continue
    compose_service = str(repo_cfg.get("compose_service", "")).strip()
    if not compose_service:
        continue
    compose_path = root / ".devcontainer" / "docker-compose.yml"
    if not compose_path.exists():
        continue
    compose_text = compose_path.read_text(encoding="utf-8", errors="ignore")
    missing = []
    service_block = re.search(rf"(?ms)^\s*{re.escape(compose_service)}:\s(.*?)(?=^\S|\Z)", compose_text)
    block_text = service_block.group(1) if service_block else ""
    for key in required_env_keys:
        key_name = str(key).strip()
        if not key_name:
            continue
        if re.search(rf"(?m)^\s*{re.escape(key_name)}\s*:", block_text):
            continue
        if re.search(rf"(?m)-\s*{re.escape(key_name)}=", block_text):
            continue
        missing.append(key_name)
    if missing:
        warnings.append(
            f"{repo_name}: missing required compose env keys for `{compose_service}`: {', '.join(missing)}."
        )

for line in warnings:
    print(f"WARN: {line}")
for line in errors:
    print(f"ERROR: {line}")
if errors:
    raise SystemExit(1)
PY
then
  pass "cross-repo policy (contracts/api-url)"
else
  fail "cross-repo policy (contracts/api-url)"
fi

echo "== Skills context checks =="
while IFS= read -r repo_name; do
  [[ -z "$repo_name" ]] && continue
  if python3 ./flow skills context --repo "$repo_name" --json >/dev/null; then
    pass "skills context for repo \`$repo_name\`"
  else
    fail "skills context for repo \`$repo_name\`"
  fi
done < <(python3 - <<'PY'
from __future__ import annotations
import json
from pathlib import Path
cfg = json.loads(Path("workspace.config.json").read_text(encoding="utf-8"))
for repo_name, repo_cfg in cfg.get("repos", {}).items():
    if isinstance(repo_cfg, dict) and str(repo_cfg.get("kind", "")).strip() == "implementation":
        print(repo_name)
PY
)

if [[ $AUTO_UP -eq 1 ]]; then
  echo "== Stack startup =="
  if [[ $BUILD_IMAGES -eq 1 ]]; then
    run_check "flow stack up --build" python3 ./flow stack up --build >/dev/null
  else
    run_check "flow stack up" python3 ./flow stack up >/dev/null
  fi
fi

run_check "flow stack ps" python3 ./flow stack ps >/dev/null

echo "== Runtime app readiness checks =="
while IFS='|' read -r repo_name runtime service_name repo_path status_cmd migrate_cmd; do
  [[ -z "$repo_name" ]] && continue
  if [[ -z "$service_name" ]]; then
    warn "$repo_name has no compose_service; skipped runtime readiness."
    continue
  fi
  if [[ -n "$status_cmd" ]]; then
    if python3 ./flow stack exec "$service_name" -- sh -lc "$status_cmd" >/dev/null; then
      pass "custom readiness status command for \`$repo_name\`"
    else
      fail "custom readiness status command for \`$repo_name\`"
    fi
    if [[ $RUN_MIGRATIONS -eq 1 && -n "$migrate_cmd" ]]; then
      if python3 ./flow stack exec "$service_name" -- sh -lc "$migrate_cmd" >/dev/null; then
        pass "custom migration/apply command for \`$repo_name\`"
      else
        fail "custom migration/apply command for \`$repo_name\`"
      fi
    elif [[ $RUN_MIGRATIONS -eq 1 ]]; then
      warn "No migration apply command configured for \`$repo_name\`."
    fi
  fi
  case "$runtime" in
    php)
      if python3 ./flow stack exec "$service_name" -- php -v >/dev/null; then
        pass "php runtime check for \`$repo_name\`"
      else
        fail "php runtime check for \`$repo_name\`"
      fi
      ;;
    node)
      if python3 ./flow stack exec "$service_name" -- node -v >/dev/null; then
        pass "node runtime check for \`$repo_name\`"
      else
        fail "node runtime check for \`$repo_name\`"
      fi
      if python3 ./flow stack exec "$service_name" -- sh -lc "ss -lntp | grep -E ':(3000|4173|5173|8000)' >/dev/null"; then
        pass "node listener check for \`$repo_name\`"
      else
        warn "No common node listener detected for \`$repo_name\`; verify service command/port."
      fi
      ;;
    python)
      if python3 ./flow stack exec "$service_name" -- python3 --version >/dev/null; then
        pass "python runtime check for \`$repo_name\`"
      else
        fail "python runtime check for \`$repo_name\`"
      fi
      if python3 ./flow stack exec "$service_name" -- sh -lc "ss -lntp | grep -E ':(8000|8001)' >/dev/null"; then
        pass "python listener check for \`$repo_name\`"
      else
        warn "No common python listener detected for \`$repo_name\`; verify service command/port."
      fi
      ;;
    *)
      warn "No runtime readiness profile for \`$repo_name\` (runtime=$runtime)."
      ;;
  esac
done < <(python3 - <<'PY'
from __future__ import annotations
import json
import os
from pathlib import Path
cfg = json.loads(Path("workspace.config.json").read_text(encoding="utf-8"))
root = Path(".").resolve()
config_path = root / os.environ.get("PREFLIGHT_CONFIG", "workspace.preflight.json")
preflight_cfg = {}
if config_path.exists():
    preflight_cfg = json.loads(config_path.read_text(encoding="utf-8"))
repo_overrides = preflight_cfg.get("repos", {}) if isinstance(preflight_cfg, dict) else {}
for repo_name, repo_cfg in cfg.get("repos", {}).items():
    if not isinstance(repo_cfg, dict):
        continue
    if str(repo_cfg.get("kind", "")).strip() != "implementation":
        continue
    runtime = str(repo_cfg.get("runtime", "")).strip().lower()
    service = str(repo_cfg.get("compose_service", "")).strip()
    path = str((root / str(repo_cfg.get("path", "")).strip()).resolve())
    override = repo_overrides.get(repo_name, {}) if isinstance(repo_overrides, dict) else {}
    status_cmd = str(override.get("readiness_status_cmd", "")).strip().replace("|", " ")
    migrate_cmd = str(override.get("migration_apply_cmd", "")).strip().replace("|", " ")
    print(f"{repo_name}|{runtime}|{service}|{path}|{status_cmd}|{migrate_cmd}")
PY
)

echo "== Integration smoke =="
if [[ $AUTO_UP -eq 1 ]]; then
  run_check "flow ci integration --profile smoke --auto-up${BUILD_IMAGES:+ --build}" \
    python3 ./flow ci integration --profile smoke --auto-up $([[ $BUILD_IMAGES -eq 1 ]] && echo --build) --json >/dev/null
else
  run_check "flow ci integration --profile smoke" \
    python3 ./flow ci integration --profile smoke --json >/dev/null
fi

if [[ $CHECK_SPEC_CI -eq 1 ]]; then
  echo "== Spec governance =="
  run_check "flow ci spec --all" python3 ./flow ci spec --all >/dev/null
else
  warn "Skipped spec governance check. Use --check-spec-ci to include 'flow ci spec --all'."
fi

echo ""
echo "Preflight summary: failures=$FAILURES warnings=$WARNINGS"
if [[ $FAILURES -gt 0 ]]; then
  echo "Environment is NOT ready."
  exit 1
fi

echo "Environment ready for onboarding."
exit 0
