from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Optional


STACK_CONFIG_FILENAME = "workspace.stack.json"
CAPABILITIES_CONFIG_FILENAME = "workspace.capabilities.json"


class StackDesignError(Exception):
    pass


def _read_json_object(path: Path, label: str) -> dict[str, object]:
    if not path.is_file():
        raise StackDesignError(f"Falta {path.name} en el root del workspace.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StackDesignError(f"{path.name} no contiene JSON valido para `{label}`: {exc}") from exc
    if not isinstance(payload, dict):
        raise StackDesignError(f"{path.name} debe contener un objeto JSON.")
    return payload


def load_stack_manifest(path: Path) -> dict[str, object]:
    payload = _read_json_object(path, "stack")
    if not isinstance(payload.get("projects", []), list):
        raise StackDesignError(f"{path.name} debe definir `projects` como lista.")
    if not isinstance(payload.get("services", []), list):
        raise StackDesignError(f"{path.name} debe definir `services` como lista.")
    if not isinstance(payload.get("capabilities", []), list):
        raise StackDesignError(f"{path.name} debe definir `capabilities` como lista.")
    return payload


def write_stack_manifest(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def load_capabilities_manifest(path: Path) -> dict[str, object]:
    payload = _read_json_object(path, "capabilities")
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, dict) or not capabilities:
        raise StackDesignError(f"{path.name} debe definir `capabilities`.")
    return payload


def resolve_capability_pack(root: Path, capability: str) -> tuple[dict[str, object], Path]:
    manifest = load_capabilities_manifest(root / CAPABILITIES_CONFIG_FILENAME)
    entry = manifest["capabilities"].get(capability)
    if not isinstance(entry, dict):
        raise StackDesignError(f"No existe capability `{capability}` en {CAPABILITIES_CONFIG_FILENAME}.")
    if not bool(entry.get("enabled", True)):
        raise StackDesignError(f"La capability `{capability}` esta deshabilitada.")
    source = str(entry.get("source", "")).strip()
    if not source:
        raise StackDesignError(f"La capability `{capability}` debe declarar `source`.")
    path = Path(source)
    if not path.is_absolute():
        path = root / path
    payload = _read_json_object(path.resolve(), capability)
    return payload, path.resolve()


def requested_capabilities(manifest: dict[str, object]) -> list[str]:
    names = [str(item).strip() for item in manifest.get("capabilities", []) if str(item).strip()]
    for project in manifest.get("projects", []):
        if not isinstance(project, dict):
            continue
        for item in project.get("capabilities", []):
            candidate = str(item).strip()
            if candidate and candidate not in names:
                names.append(candidate)
    return names


def _default_project_name(prompt: str, kind: str) -> str:
    if kind == "api":
        return "api"
    if kind == "web":
        return "web"
    match = re.search(r"\b(llamad[oa]|nombre|name)\s+([A-Za-z0-9_-]+)", prompt, flags=re.IGNORECASE)
    if match:
        return match.group(2).strip().lower()
    return kind


def _default_port(runtime: str) -> Optional[int]:
    return {
        "go-api": 8080,
        "php": 8000,
        "pnpm": 5173,
    }.get(runtime)


def _merge_dict(base: dict[str, object], override: dict[str, object]) -> dict[str, object]:
    merged = json.loads(json.dumps(base))
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def _service_binding_overrides(runtime: str, service_name: str) -> dict[str, object]:
    if runtime == "go-api" and service_name == "postgres":
        return {
            "environment": {
                "DATABASE_URL": "postgres://app:app@postgres:5432/app_dev?sslmode=disable"
            },
            "depends_on": {
                "postgres": {
                    "condition": "service_healthy"
                }
            }
        }
    if runtime == "go-api" and service_name == "mongo":
        return {
            "environment": {
                "MONGODB_URL": "mongodb://mongo:27017/app_dev"
            },
            "depends_on": {
                "mongo": {
                    "condition": "service_started"
                }
            }
        }
    return {}


def design_stack_from_prompt(prompt: str) -> dict[str, object]:
    lowered = prompt.lower()
    manifest: dict[str, object] = {
        "schema_version": 1,
        "source_prompt": prompt.strip(),
        "projects": [],
        "services": [],
        "capabilities": [],
        "notes": [],
    }

    projects: list[dict[str, object]] = []
    services: list[dict[str, object]] = []
    capabilities: list[str] = []

    api_runtime: Optional[str] = None
    if any(keyword in lowered for keyword in ["golang", "go api", "api en go", "api in go", "api en golang"]):
        api_runtime = "go-api"
    elif any(keyword in lowered for keyword in ["laravel", "php api", "api en php", "api en laravel"]):
        api_runtime = "php"

    if api_runtime is not None:
        api_name = _default_project_name(prompt, "api")
        api_project = {
            "name": api_name,
            "path": api_name,
            "runtime": api_runtime,
            "port": _default_port(api_runtime),
            "capabilities": [],
            "service_bindings": [],
            "compose_overrides": {},
        }
        projects.append(api_project)

    if any(keyword in lowered for keyword in ["frontend", "web app", "vite", "react app", "react frontend"]):
        web_name = _default_project_name(prompt, "web")
        projects.append(
            {
                "name": web_name,
                "path": web_name,
                "runtime": "pnpm",
                "port": _default_port("pnpm"),
                "capabilities": [],
                "service_bindings": [],
                "compose_overrides": {},
            }
        )

    if any(keyword in lowered for keyword in ["postgresql", "postgres", "postgre"]):
        services.append({"name": "postgres", "runtime": "postgres-service"})
        for project in projects:
            if str(project.get("runtime")) == "go-api":
                project["service_bindings"].append("postgres")
                project["compose_overrides"] = _merge_dict(
                    dict(project.get("compose_overrides", {})),
                    _service_binding_overrides("go-api", "postgres"),
                )

    if any(keyword in lowered for keyword in ["mongodb", "mongo db", "mongo"]):
        services.append({"name": "mongo", "runtime": "mongo-service"})
        for project in projects:
            if str(project.get("runtime")) == "go-api":
                project["service_bindings"].append("mongo")
                project["compose_overrides"] = _merge_dict(
                    dict(project.get("compose_overrides", {})),
                    _service_binding_overrides("go-api", "mongo"),
                )

    if "graphql" in lowered:
        capabilities.append("graphql")
        for project in projects:
            if str(project.get("runtime")) in {"go-api", "php"}:
                project["capabilities"].append("graphql")

    if not projects and not services:
        raise StackDesignError(
            "No pude inferir un stack valido del prompt. Prueba con algo como "
            "`quiero una api en golang con postgresql y graphql`."
        )

    manifest["projects"] = projects
    manifest["services"] = services
    manifest["capabilities"] = capabilities
    manifest["notes"] = [
        "V1 usa inferencia heuristica local; no invoca un modelo externo.",
        "Los servicios standalone se materializan en docker-compose sin crear repos falsos.",
    ]
    return manifest


def _format_text(value: str, substitutions: dict[str, str]) -> str:
    return value.format(**substitutions)


def render_foundation_spec(pack: dict[str, object], substitutions: dict[str, str], targets: list[str]) -> list[tuple[Path, str]]:
    items = pack.get("foundation_specs", [])
    rendered: list[tuple[Path, str]] = []
    if not isinstance(items, list):
        return rendered
    for item in items:
        if not isinstance(item, dict):
            continue
        path = Path(_format_text(str(item.get("path", "")).strip(), substitutions))
        name = _format_text(str(item.get("name", "")).strip(), substitutions)
        description = _format_text(str(item.get("description", "")).strip(), substitutions)
        owner = _format_text(str(item.get("owner", "platform")).strip(), substitutions)
        body_items = item.get("body", [])
        if not path or not name or not isinstance(body_items, list):
            continue
        body = "\n".join(_format_text(str(line), substitutions) for line in body_items)
        frontmatter = [
            "---",
            f"name: {name}",
            f"description: {description}",
            "status: approved",
            f"owner: {owner}",
            "targets:",
        ]
        for target in targets:
            frontmatter.append(f"  - {target}")
        frontmatter.append("---")
        text = "\n".join(frontmatter) + "\n\n" + body.strip() + "\n"
        rendered.append((path, text))
    return rendered


def _current_repo_config(load_workspace_config: Callable[[], dict[str, object]]) -> dict[str, dict[str, object]]:
    payload = load_workspace_config()
    repos = payload.get("repos", {})
    if not isinstance(repos, dict):
        raise StackDesignError("workspace.config.json debe definir `repos`.")
    return repos


def apply_project_definition(
    project: dict[str, object],
    *,
    root: Path,
    root_repo: str,
    workspace_config_file: Path,
    load_workspace_config: Callable[[], dict[str, object]],
    load_skills_config: Callable[[], dict[str, object]],
    skills_entries,
    normalize_repo_path: Callable[[str], str],
    validate_identifier: Callable[[str, str], str],
    ensure_project_directory,
    repo_placeholder_text,
    resolve_runtime_pack,
    add_service_to_compose,
    rel: Callable[[Path], str],
) -> dict[str, object]:
    repo_name = validate_identifier(str(project.get("name", "")).strip(), "nombre del proyecto")
    repo_path = normalize_repo_path(str(project.get("path", repo_name)))
    runtime = str(project.get("runtime", "")).strip()
    runtime_pack = resolve_runtime_pack(root, runtime, repo_name, repo_path)
    if str(runtime_pack.get("runtime_kind", "project")) != "project":
        raise StackDesignError(f"El runtime `{runtime}` no es un runtime de proyecto.")

    current_workspace = load_workspace_config()
    current_repos = current_workspace.get("repos", {})
    if not isinstance(current_repos, dict):
        raise StackDesignError("workspace.config.json debe definir `repos`.")
    if repo_name in current_repos:
        return {"name": repo_name, "status": "skipped", "reason": "repo already registered"}

    destination = root / repo_path
    ensure_project_directory(destination, use_existing=bool(project.get("use_existing_dir", False)), rel=rel)

    agents_text, readme_text = repo_placeholder_text(root_repo, repo_name, runtime_pack["agent_skill_refs"])
    if not (destination / "AGENTS.md").exists():
        (destination / "AGENTS.md").write_text(agents_text, encoding="utf-8")
    if not (destination / "README.md").exists():
        (destination / "README.md").write_text(readme_text, encoding="utf-8")

    for directory in runtime_pack["placeholder_dirs"]:
        target_dir = destination / str(directory)
        target_dir.mkdir(parents=True, exist_ok=True)
        gitkeep = target_dir / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.write_text("", encoding="utf-8")

    for relative_path, content in runtime_pack["placeholder_files"].items():
        target_file = destination / relative_path
        if not target_file.exists():
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(content, encoding="utf-8")

    compose_service = validate_identifier(str(project.get("compose_service") or repo_name), "nombre del servicio")
    compose_config = runtime_pack.get("compose")
    compose_overrides = project.get("compose_overrides", {})
    if isinstance(compose_config, dict) and isinstance(compose_overrides, dict):
        compose_config = _merge_dict(compose_config, compose_overrides)

    updated_workspace = load_workspace_config()
    repos = updated_workspace["repos"]
    if not isinstance(repos, dict):
        raise StackDesignError("workspace.config.json debe definir `repos`.")

    repos[repo_name] = {
        "path": repo_path,
        "compose_service": compose_service,
        "kind": "implementation",
        "runtime": runtime,
        "repo_strategy": "plain",
        "slice_prefix": repo_name.replace("_", "-"),
        "default_targets": list(project.get("default_targets") or runtime_pack["default_targets"]),
        "target_roots": list(project.get("target_roots") or runtime_pack["target_roots"]),
        "contract_roots": list(runtime_pack["test_required_roots"]),
        "test_required_roots": list(runtime_pack["test_required_roots"]),
        "agent_skill_refs": list(runtime_pack["agent_skill_refs"]),
        "test_runner": str(project.get("test_runner") or runtime_pack["test_runner"]),
    }
    if runtime_pack.get("test_hint"):
        repos[repo_name]["test_hint"] = runtime_pack["test_hint"]

    workspace_config_file.write_text(
        json.dumps(updated_workspace, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    if isinstance(compose_config, dict):
        add_service_to_compose(
            compose_service,
            repo_path,
            runtime,
            int(project["port"]) if project.get("port") is not None else None,
            compose_config,
        )

    missing_skill_refs: list[str] = []
    try:
        skills_payload = load_skills_config()
        entries, errors = skills_entries(skills_payload)
        if errors:
            raise StackDesignError("\n".join(errors))
        known = {str(entry["name"]) for entry in entries}
        missing_skill_refs = [ref for ref in runtime_pack["agent_skill_refs"] if ref not in known]
    except Exception:
        missing_skill_refs = list(runtime_pack["agent_skill_refs"])

    return {
        "name": repo_name,
        "status": "added",
        "path": repo_path,
        "runtime": runtime,
        "compose_service": compose_service,
        "missing_skill_refs": missing_skill_refs,
    }


def command_stack_design(
    args,
    *,
    stack_config_file: Path,
    utc_now: Callable[[], str],
    json_dumps: Callable[[object], str],
) -> int:
    manifest = design_stack_from_prompt(args.prompt)
    manifest["designed_at"] = utc_now()
    write_stack_manifest(stack_config_file, manifest)
    payload = {
        "stack_manifest": str(stack_config_file.name),
        "design": manifest,
    }
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
        return 0
    print(stack_config_file.name)
    return 0


def command_stack_plan(
    args,
    *,
    root: Path,
    stack_config_file: Path,
    workspace_config_file: Path,
    load_workspace_config: Callable[[], dict[str, object]],
    resolve_capability_pack,
    resolve_runtime_pack,
    json_dumps: Callable[[object], str],
) -> int:
    manifest = load_stack_manifest(stack_config_file)
    current_repos = _current_repo_config(load_workspace_config)
    compose_text = (root / ".devcontainer" / "docker-compose.yml").read_text(encoding="utf-8")
    actions: list[dict[str, object]] = []

    for service in manifest.get("services", []):
        if not isinstance(service, dict):
            continue
        name = str(service.get("name", "")).strip()
        runtime = str(service.get("runtime", "")).strip()
        runtime_pack = resolve_runtime_pack(root, runtime, name, name)
        actions.append(
            {
                "type": "service",
                "name": name,
                "runtime": runtime,
                "runtime_kind": runtime_pack.get("runtime_kind"),
                "status": "existing" if f"\n  {name}:\n" in compose_text else "planned",
            }
        )

    for project in manifest.get("projects", []):
        if not isinstance(project, dict):
            continue
        name = str(project.get("name", "")).strip()
        runtime = str(project.get("runtime", "")).strip()
        runtime_pack = resolve_runtime_pack(root, runtime, name, str(project.get("path", name) or name))
        actions.append(
            {
                "type": "project",
                "name": name,
                "runtime": runtime,
                "runtime_kind": runtime_pack.get("runtime_kind"),
                "status": "existing" if name in current_repos else "planned",
                "capabilities": list(project.get("capabilities", [])),
                "service_bindings": list(project.get("service_bindings", [])),
            }
        )

    substitutions = {
        "primary_project": str(manifest.get("projects", [{}])[0].get("name", "api")) if manifest.get("projects") else "api",
        "primary_database": str(manifest.get("services", [{}])[0].get("name", "database")) if manifest.get("services") else "database",
    }
    for capability in requested_capabilities(manifest):
        pack, _ = resolve_capability_pack(root, capability)
        rendered = render_foundation_spec(pack, substitutions, _default_targets_for_manifest(manifest))
        for spec_path, _ in rendered:
            absolute = root / spec_path
            actions.append(
                {
                    "type": "foundation-spec",
                    "name": capability,
                    "path": str(spec_path),
                    "status": "existing" if absolute.exists() else "planned",
                }
            )

    payload = {
        "stack_manifest": str(workspace_config_file.parent / stack_config_file.name),
        "source_prompt": manifest.get("source_prompt", ""),
        "actions": actions,
    }
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
        return 0
    print(json_dumps(payload))
    return 0


def _default_targets_for_manifest(manifest: dict[str, object]) -> list[str]:
    project_targets: list[str] = []
    for project in manifest.get("projects", []):
        if not isinstance(project, dict):
            continue
        path = str(project.get("path", project.get("name", "api"))).strip() or str(project.get("name", "api"))
        runtime = str(project.get("runtime", "")).strip()
        if runtime == "go-api":
            project_targets.extend(
                [
                    f"../../{path}/cmd/**",
                    f"../../{path}/internal/**",
                    f"../../{path}/tests/**",
                ]
            )
        elif runtime == "php":
            project_targets.extend(
                [
                    f"../../{path}/app/**",
                    f"../../{path}/routes/**",
                    f"../../{path}/tests/**",
                ]
            )
        elif runtime == "pnpm":
            project_targets.extend(
                [
                    f"../../{path}/src/**",
                    f"../../{path}/public/**",
                    f"../../{path}/tests/**",
                ]
            )
    return project_targets or ["../../.devcontainer/**", "../../specs/**"]


def command_stack_apply(
    args,
    *,
    root: Path,
    root_repo: str,
    stack_config_file: Path,
    workspace_config_file: Path,
    load_workspace_config: Callable[[], dict[str, object]],
    load_skills_config: Callable[[], dict[str, object]],
    skills_entries,
    normalize_repo_path: Callable[[str], str],
    validate_identifier: Callable[[str, str], str],
    ensure_project_directory,
    repo_placeholder_text,
    resolve_runtime_pack,
    add_service_to_compose,
    add_standalone_service_to_compose,
    resolve_capability_pack,
    rel: Callable[[Path], str],
    utc_now: Callable[[], str],
    json_dumps: Callable[[object], str],
) -> int:
    manifest = load_stack_manifest(stack_config_file)
    results = {"services": [], "projects": [], "foundation_specs": []}

    for service in manifest.get("services", []):
        if not isinstance(service, dict):
            continue
        name = validate_identifier(str(service.get("name", "")).strip(), "nombre del servicio")
        runtime = str(service.get("runtime", "")).strip()
        runtime_pack = resolve_runtime_pack(root, runtime, name, name)
        if str(runtime_pack.get("runtime_kind", "project")) != "service":
            raise StackDesignError(f"El runtime `{runtime}` no es un runtime de servicio.")
        compose_text = (root / ".devcontainer" / "docker-compose.yml").read_text(encoding="utf-8")
        if f"\n  {name}:\n" in compose_text:
            results["services"].append({"name": name, "status": "skipped", "reason": "service already exists"})
            continue
        compose_config = runtime_pack.get("compose")
        if not isinstance(compose_config, dict):
            raise StackDesignError(f"El runtime `{runtime}` debe declarar `compose` para servicios standalone.")
        add_standalone_service_to_compose(root / ".devcontainer" / "docker-compose.yml", name, runtime, compose_config)
        results["services"].append({"name": name, "status": "added", "runtime": runtime})

    for project in manifest.get("projects", []):
        if not isinstance(project, dict):
            continue
        result = apply_project_definition(
            project,
            root=root,
            root_repo=root_repo,
            workspace_config_file=workspace_config_file,
            load_workspace_config=load_workspace_config,
            load_skills_config=load_skills_config,
            skills_entries=skills_entries,
            normalize_repo_path=normalize_repo_path,
            validate_identifier=validate_identifier,
            ensure_project_directory=ensure_project_directory,
            repo_placeholder_text=repo_placeholder_text,
            resolve_runtime_pack=resolve_runtime_pack,
            add_service_to_compose=add_service_to_compose,
            rel=rel,
        )
        results["projects"].append(result)

    substitutions = {
        "primary_project": str(manifest.get("projects", [{}])[0].get("name", "api")) if manifest.get("projects") else "api",
        "primary_database": str(manifest.get("services", [{}])[0].get("name", "database")) if manifest.get("services") else "database",
    }
    foundation_targets = _default_targets_for_manifest(manifest)
    for capability in requested_capabilities(manifest):
        pack, _ = resolve_capability_pack(root, capability)
        for relative_path, text in render_foundation_spec(pack, substitutions, foundation_targets):
            destination = root / relative_path
            if destination.exists():
                results["foundation_specs"].append({"path": str(relative_path), "status": "skipped"})
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(text, encoding="utf-8")
            results["foundation_specs"].append({"path": str(relative_path), "status": "created"})

    manifest["applied_at"] = utc_now()
    manifest["generated_specs"] = [item["path"] for item in results["foundation_specs"] if item["status"] == "created"]
    write_stack_manifest(stack_config_file, manifest)

    payload = {
        "stack_manifest": stack_config_file.name,
        "results": results,
    }
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
        return 0
    print(json_dumps(payload))
    return 0
