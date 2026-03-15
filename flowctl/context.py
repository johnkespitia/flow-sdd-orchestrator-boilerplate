from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


def env_first(*names: str, default: Optional[str] = None) -> Optional[str]:
    import os

    for name in names:
        value = os.environ.get(name)
        if value is not None:
            return value
    return default


def load_json_object(path: Path, label: str) -> dict[str, object]:
    if not path.is_file():
        raise SystemExit(f"Falta {path.name} en el root del workspace.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path.name} no contiene JSON valido: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"{path.name} debe contener un objeto JSON en el root.")
    return payload


def load_workspace_config(path: Path) -> dict[str, object]:
    data = load_json_object(path, "workspace")
    project = data.get("project")
    repos = data.get("repos")
    if not isinstance(project, dict) or not isinstance(repos, dict) or not repos:
        raise SystemExit(f"{path.name} debe definir `project` y `repos`.")
    root_repo = project.get("root_repo")
    if not isinstance(root_repo, str) or root_repo not in repos:
        raise SystemExit(f"{path.name} debe declarar `project.root_repo` presente en `repos`.")
    return data


def load_skills_config(path: Path) -> dict[str, object]:
    payload = load_json_object(path, "skills")
    providers = payload.get("providers")
    entries = payload.get("entries")
    if not isinstance(providers, dict) or not isinstance(entries, list):
        raise SystemExit(f"{path.name} debe definir `providers` y `entries`.")
    return payload


def load_providers_config(path: Path) -> dict[str, object]:
    payload = load_json_object(path, "providers")
    for category in ["release", "infra"]:
        section = payload.get(category)
        if not isinstance(section, dict):
            raise SystemExit(f"{path.name} debe definir la seccion `{category}`.")
        providers = section.get("providers")
        if not isinstance(providers, dict) or not providers:
            raise SystemExit(f"{path.name} debe definir `{category}.providers`.")
        default_provider = section.get("default_provider")
        if not isinstance(default_provider, str) or default_provider not in providers:
            raise SystemExit(
                f"{path.name} debe definir `{category}.default_provider` presente en `{category}.providers`."
            )
    return payload


def load_secrets_config(path: Path) -> dict[str, object]:
    payload = load_json_object(path, "secrets")
    providers = payload.get("providers")
    targets = payload.get("targets")
    if not isinstance(providers, dict):
        raise SystemExit(f"{path.name} debe definir `providers`.")
    if not isinstance(targets, dict):
        raise SystemExit(f"{path.name} debe definir `targets`.")
    default_provider = payload.get("default_provider")
    if not isinstance(default_provider, str) or default_provider not in providers:
        raise SystemExit(f"{path.name} debe definir `default_provider` presente en `providers`.")
    return payload


def build_workspace_context(root: Path, runtimes_config_filename: str) -> dict[str, object]:
    workspace_config_file = root / "workspace.config.json"
    skills_config_file = root / "workspace.skills.json"
    providers_config_file = root / "workspace.providers.json"
    secrets_config_file = root / "workspace.secrets.json"
    runtimes_config_file = root / runtimes_config_filename

    workspace_config = load_workspace_config(workspace_config_file)
    project_config = workspace_config["project"]
    repo_config = workspace_config["repos"]
    root_repo = str(project_config["root_repo"])
    workspace_path = env_first("FLOW_WORKSPACE_PATH", "PLG_WORKSPACE_PATH", default="/workspace") or "/workspace"

    return {
        "WORKSPACE_CONFIG_FILE": workspace_config_file,
        "SKILLS_CONFIG_FILE": skills_config_file,
        "PROVIDERS_CONFIG_FILE": providers_config_file,
        "SECRETS_CONFIG_FILE": secrets_config_file,
        "RUNTIMES_CONFIG_FILE": runtimes_config_file,
        "WORKSPACE_CONFIG": workspace_config,
        "PROJECT_CONFIG": project_config,
        "REPO_CONFIG": repo_config,
        "PROJECT_NAME": str(project_config.get("display_name") or root.name),
        "ROOT_REPO": root_repo,
        "REPO_NAMES": list(repo_config),
        "WORKSPACE_SERVICE": env_first("FLOW_WORKSPACE_SERVICE", "PLG_WORKSPACE_SERVICE", default="workspace") or "workspace",
        "WORKSPACE_PATH": workspace_path,
        "DEFAULT_COMPOSE_PROJECT": env_first(
            "FLOW_COMPOSE_PROJECT",
            "PLG_COMPOSE_PROJECT",
            default=f"{root_repo if root.name == Path(workspace_path).name else root.name}_devcontainer",
        ),
        "HOST_ROOT_HINT": Path(env_first("FLOW_HOST_ROOT", "PLG_HOST_ROOT", default=str(root)) or root).expanduser(),
        "WORKTREE_ROOT": Path(
            env_first("FLOW_WORKTREE_ROOT", "PLG_WORKTREE_ROOT", default=str(root / ".worktrees")) or (root / ".worktrees")
        ).expanduser(),
        "DEFAULT_TARGETS": {
            repo: list(config.get("default_targets", []))
            for repo, config in repo_config.items()
        },
        "TARGET_ROOTS": {
            repo: set(config.get("target_roots", []))
            for repo, config in repo_config.items()
        },
        "TEST_REQUIRED_ROOTS": {
            repo: set(config.get("test_required_roots", config.get("target_roots", [])))
            for repo, config in repo_config.items()
        },
        "CONTRACT_ROOTS": {
            repo: set(config.get("contract_roots", config.get("test_required_roots", config.get("target_roots", []))))
            for repo, config in repo_config.items()
        },
        "REPO_PREFIXES": {
            repo: f"../../{config['path'].strip('/')}/"
            for repo, config in repo_config.items()
            if repo != root_repo and str(config.get("path", ".")).strip("/") not in {"", "."}
        },
        "TEST_HINTS": {
            repo: str(config["test_hint"])
            for repo, config in repo_config.items()
            if config.get("test_hint")
        },
    }
