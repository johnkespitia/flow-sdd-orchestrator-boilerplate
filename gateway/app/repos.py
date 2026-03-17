from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_workspace_repo_catalog(workspace_root: Path) -> tuple[str, dict[str, dict[str, Any]]]:
    config_path = workspace_root / "workspace.config.json"
    if not config_path.is_file():
        raise RuntimeError(f"Falta workspace.config.json en {workspace_root}.")

    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"workspace.config.json no contiene JSON valido: {exc}.") from exc

    project = payload.get("project")
    repos = payload.get("repos")
    if not isinstance(project, dict) or not isinstance(repos, dict) or not repos:
        raise RuntimeError("workspace.config.json debe definir `project` y `repos`.")

    root_repo = str(project.get("root_repo", "")).strip()
    if not root_repo or root_repo not in repos:
        raise RuntimeError("workspace.config.json debe definir `project.root_repo` presente en `repos`.")

    normalized: dict[str, dict[str, Any]] = {}
    for repo_name, raw_repo in repos.items():
        if isinstance(raw_repo, dict):
            normalized[str(repo_name)] = raw_repo
    return root_repo, normalized


def repo_aliases(repo_name: str, repo_config: dict[str, Any], *, root_repo: str) -> list[str]:
    aliases = {repo_name}

    if repo_name == root_repo:
        aliases.update({"root", "root-repo", "root_repo", "workspace", "workspace-root", "."})

    repo_path = str(repo_config.get("path", "")).strip().strip("/")
    if repo_path and repo_path != ".":
        aliases.add(repo_path)
        aliases.add(Path(repo_path).name)

    compose_service = str(repo_config.get("compose_service", "")).strip()
    if compose_service:
        aliases.add(compose_service)

    for field in ("code", "gateway_code"):
        value = str(repo_config.get(field, "")).strip()
        if value:
            aliases.add(value)

    for field in ("aliases", "gateway_aliases"):
        raw_value = repo_config.get(field, [])
        if isinstance(raw_value, str):
            aliases.add(raw_value.strip())
            continue
        if isinstance(raw_value, list):
            aliases.update(str(item).strip() for item in raw_value if str(item).strip())

    return sorted(alias for alias in aliases if alias)


def repo_default_code(repo_name: str, repo_config: dict[str, Any], *, root_repo: str) -> str:
    if repo_name == root_repo:
        return "root"
    for field in ("gateway_code", "code"):
        value = str(repo_config.get(field, "")).strip()
        if value:
            return value
    return repo_name


def repo_catalog_payload(workspace_root: Path) -> dict[str, Any]:
    root_repo, repos = load_workspace_repo_catalog(workspace_root)
    items: list[dict[str, Any]] = []
    available_codes: list[str] = []

    for repo_name, repo_config in repos.items():
        aliases = repo_aliases(repo_name, repo_config, root_repo=root_repo)
        default_code = repo_default_code(repo_name, repo_config, root_repo=root_repo)
        available_codes.extend(aliases)
        items.append(
            {
                "repo": repo_name,
                "code": default_code,
                "accepted_refs": aliases,
                "path": str(repo_config.get("path", ".")).strip() or ".",
                "kind": str(repo_config.get("kind", "")).strip() or None,
                "compose_service": str(repo_config.get("compose_service", "")).strip() or None,
                "is_root": repo_name == root_repo,
            }
        )

    items.sort(key=lambda item: (not bool(item["is_root"]), str(item["repo"])))
    return {
        "root_repo": root_repo,
        "repos": items,
        "available_codes": sorted({code for code in available_codes if code}),
    }


def resolve_repo_references(payload: dict[str, Any], *, workspace_root: Path) -> list[str]:
    references: list[str] = []
    for key in ("repos", "repo", "repo_codes", "repo_code"):
        raw = payload.get(key)
        if isinstance(raw, str):
            references.extend(item.strip() for item in raw.split(",") if item.strip())
        elif isinstance(raw, list):
            references.extend(str(item).strip() for item in raw if str(item).strip())

    root_repo, repos = load_workspace_repo_catalog(workspace_root)
    alias_map: dict[str, str | None] = {}
    available_codes: set[str] = set()

    for repo_name, repo_config in repos.items():
        for alias in repo_aliases(repo_name, repo_config, root_repo=root_repo):
            normalized = alias.lower()
            available_codes.add(alias)
            mapped = alias_map.get(normalized)
            if mapped is None and normalized in alias_map:
                continue
            if mapped is None:
                alias_map[normalized] = repo_name
            elif mapped != repo_name:
                alias_map[normalized] = None

    resolved: list[str] = []
    seen: set[str] = set()
    for reference in references:
        normalized = reference.strip().lower()
        if not normalized:
            continue
        repo_name = alias_map.get(normalized)
        if repo_name is None:
            available = ", ".join(sorted(available_codes))
            raise ValueError(f"Repo/codigo no soportado: `{reference}`. Disponibles: {available}.")
        if repo_name not in seen:
            resolved.append(repo_name)
            seen.add(repo_name)
    return resolved
