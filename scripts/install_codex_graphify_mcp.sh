#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v codex >/dev/null 2>&1; then
  echo "codex CLI not found in PATH." >&2
  exit 127
fi

readarray -t GRAPHIFY_CONFIG < <(
  python3 - "$ROOT_DIR/workspace.config.json" "${1:-}" <<'PY'
import json
import posixpath
import re
import sys

payload = json.loads(open(sys.argv[1], encoding="utf-8").read())
root_repo = str(payload.get("project", {}).get("root_repo") or "softos-workspace")
repo = str(sys.argv[2] or root_repo)
repos = payload.get("repos", {})
if repo not in repos or not isinstance(repos[repo], dict):
    raise SystemExit(f"Repo {repo!r} is not registered in workspace.config.json")
repo_path = str(repos[repo].get("path") or ".").strip("/")
output_dir = str(payload.get("code_graph", {}).get("output_dir") or "graphify-out").strip("/")
slug = re.sub(r"[^A-Za-z0-9_-]+", "-", repo).strip("-") or "repo"
print(repo)
print(slug)
print(posixpath.join("/workspace", repo_path, output_dir))
PY
)
REPO_NAME="${GRAPHIFY_CONFIG[0]}"
REPO_SLUG="${GRAPHIFY_CONFIG[1]}"
GRAPH_PATH="${GRAPHIFY_CONFIG[2]}"
SERVER_NAME="${2:-softos-${REPO_SLUG}-graphify}"

echo "Installing Codex MCP server '${SERVER_NAME}' for repo '${REPO_NAME}'."
echo "This writes to Codex user config. Existing servers with the same name must be removed first."

codex mcp add "${SERVER_NAME}" \
  -- "${ROOT_DIR}/scripts/workspace_exec.sh" \
  graphify-mcp "${GRAPH_PATH}"

codex mcp get "${SERVER_NAME}"
