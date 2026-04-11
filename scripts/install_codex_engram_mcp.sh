#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER_NAME="${1:-softos-engram}"

if ! command -v codex >/dev/null 2>&1; then
  echo "codex CLI not found in PATH." >&2
  exit 127
fi

PROJECT="$(
  python3 - "$ROOT_DIR/workspace.config.json" <<'PY'
import json
import sys

payload = json.loads(open(sys.argv[1], encoding="utf-8").read())
memory = payload.get("memory") if isinstance(payload.get("memory"), dict) else {}
agent = memory.get("agent") if isinstance(memory.get("agent"), dict) else {}
project = str(agent.get("project") or payload.get("project", {}).get("root_repo") or "softos-workspace").strip()
print(project or "softos-workspace")
PY
)"

echo "Installing Codex MCP server '${SERVER_NAME}' for project '${PROJECT}'."
echo "This writes to Codex user config. Existing servers with the same name must be removed first."

codex mcp add "${SERVER_NAME}" \
  --env "ENGRAM_PROJECT=${PROJECT}" \
  --env "ENGRAM_DATA_DIR=/workspace/.flow/memory/engram" \
  -- "${ROOT_DIR}/scripts/workspace_exec.sh" engram mcp

codex mcp get "${SERVER_NAME}"
