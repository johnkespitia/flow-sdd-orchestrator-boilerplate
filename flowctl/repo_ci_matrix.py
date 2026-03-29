from __future__ import annotations

import json
from pathlib import Path


def load_runtime_pack_map(workspace_root: Path) -> dict[str, dict[str, object]]:
    runtimes_registry: dict[str, object] = {}
    runtimes_index: dict[str, dict[str, object]] = {}
    runtimes_file = workspace_root / "workspace.runtimes.json"
    if runtimes_file.exists():
        try:
            runtimes_registry = json.loads(runtimes_file.read_text(encoding="utf-8")).get("runtimes", {})
        except Exception:
            runtimes_registry = {}

    def load_runtime_pack(runtime_name: str) -> dict[str, object]:
        if not runtime_name:
            return {}
        if runtime_name in runtimes_index:
            return runtimes_index[runtime_name]
        source = ""
        entry = runtimes_registry.get(runtime_name, {})
        if isinstance(entry, dict):
            source = str(entry.get("source", "")).strip()
        candidates = []
        if source:
            candidates.append(Path(source))
        candidates.append(workspace_root / "runtimes" / f"{runtime_name}.runtime.json")
        for candidate in candidates:
            if not candidate.is_file():
                continue
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    runtimes_index[runtime_name] = payload
                    return payload
            except Exception:
                continue
        runtimes_index[runtime_name] = {}
        return {}

    repos = {}
    workspace_config = json.loads((workspace_root / "workspace.config.json").read_text(encoding="utf-8"))
    raw_repos = workspace_config.get("repos", {})
    if isinstance(raw_repos, dict):
        repos = raw_repos
    for repo_cfg in repos.values():
        if not isinstance(repo_cfg, dict):
            continue
        load_runtime_pack(str(repo_cfg.get("runtime", "")).strip())
    return runtimes_index


def infer_tools(runtime_name: str, repo_cfg: dict[str, object], runtime_pack: dict[str, object]) -> tuple[bool, bool, bool, bool]:
    runner = str(repo_cfg.get("test_runner", runtime_pack.get("test_runner", ""))).strip().lower()
    ci_cfg = repo_cfg.get("ci")
    if not isinstance(ci_cfg, dict):
        ci_cfg = runtime_pack.get("ci", {})
    tokens: list[str] = []
    if isinstance(ci_cfg, dict):
        for step in ("install", "lint", "test", "build"):
            cmd = ci_cfg.get(step)
            if isinstance(cmd, list):
                tokens.extend(str(part).strip().lower() for part in cmd if isinstance(part, str))
    runtime_lower = runtime_name.lower()
    token_set = set(tokens)
    needs_node = (
        runner == "pnpm"
        or any(item in token_set for item in {"pnpm", "npm", "npx", "node"})
        or "node" in runtime_lower
    )
    needs_php = (
        runner == "php"
        or any(item in token_set for item in {"php", "composer", "phpunit", "artisan"})
        or "php" in runtime_lower
    )
    needs_go = (
        runner == "go"
        or "go" in token_set
        or runtime_lower.startswith("go")
        or runtime_lower.endswith("-go")
    )
    needs_python = (
        runner == "pytest"
        or any(item in token_set for item in {"python", "python3", "pip", "pip3", "pytest", "uv"})
        or "python" in runtime_lower
    )
    return needs_node, needs_php, needs_go, needs_python


def build_repo_ci_matrices(workspace_config: dict[str, object], runtime_packs: dict[str, dict[str, object]]) -> dict[str, object]:
    generic: list[dict[str, object]] = []
    delegated: list[dict[str, object]] = []
    repos = workspace_config.get("repos", {})
    if not isinstance(repos, dict):
        return {
            "generic": {"include": []},
            "delegated": {"include": []},
            "has_generic": False,
            "has_delegated": False,
        }

    for repo_name in sorted(repos):
        repo_cfg = repos.get(repo_name, {})
        if not isinstance(repo_cfg, dict):
            continue
        if str(repo_cfg.get("kind", "")).strip().lower() == "root":
            continue

        runtime_name = str(repo_cfg.get("runtime", "")).strip()
        runtime_pack = runtime_packs.get(runtime_name, {})
        needs_node, needs_php, needs_go, needs_python = infer_tools(runtime_name, repo_cfg, runtime_pack)
        ci_cfg = repo_cfg.get("ci", {})
        if not isinstance(ci_cfg, dict):
            ci_cfg = {}
        ci_mode = str(ci_cfg.get("mode", "")).strip().lower() or "inline"
        entry = {
            "repo": repo_name,
            "path": str(repo_cfg.get("path", repo_name)).strip() or repo_name,
            "runtime": runtime_name or "unknown",
            "needs_node": needs_node,
            "needs_php": needs_php,
            "needs_go": needs_go,
            "needs_python": needs_python,
        }
        if ci_mode == "workflow-dispatch":
            delegated.append(
                {
                    **entry,
                    "workflow": str(ci_cfg.get("workflow", "")).strip(),
                    "workflow_repository": str(ci_cfg.get("workflow_repository", "")).strip(),
                    "trigger_mode": str(ci_cfg.get("trigger_mode", "")).strip() or "workflow_dispatch_only",
                    "inputs": ci_cfg.get("inputs", {}) if isinstance(ci_cfg.get("inputs", {}), dict) else {},
                }
            )
            continue
        generic.append(entry)

    return {
        "generic": {"include": generic},
        "delegated": {"include": delegated},
        "has_generic": bool(generic),
        "has_delegated": bool(delegated),
    }
