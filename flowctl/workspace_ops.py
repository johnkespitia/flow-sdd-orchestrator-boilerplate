from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable, Optional


def normalize_repo_path(value: str) -> str:
    raw = value.strip()
    candidate = Path(raw)
    if not raw or candidate.is_absolute():
        raise SystemExit("Debes indicar un path relativo valido para el proyecto.")
    normalized = candidate.as_posix().strip("/")
    if not normalized or normalized in {".", ".."}:
        raise SystemExit("Debes indicar un path relativo valido para el proyecto.")
    parts = Path(normalized).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise SystemExit("El path del proyecto no puede salir del workspace ni usar segmentos vacios.")
    return "/".join(parts)


def validate_identifier(value: str, label: str) -> str:
    candidate = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", candidate):
        raise SystemExit(f"El {label} debe usar solo letras, numeros, guiones o guiones bajos.")
    return candidate


def repo_path_conflicts(repo_path: str, *, repo_config: dict[str, dict[str, object]]) -> Optional[str]:
    for repo, config in repo_config.items():
        existing_raw = str(config.get("path", ".")).strip()
        if existing_raw in {"", "."}:
            continue
        existing = normalize_repo_path(existing_raw)
        if repo_path == existing:
            return f"El path `{repo_path}` ya pertenece al repo `{repo}`."
        if repo_path.startswith(existing + "/"):
            return f"El path `{repo_path}` queda dentro del repo existente `{repo}` ({existing})."
        if existing.startswith(repo_path + "/"):
            return f"El path `{repo_path}` contendria al repo existente `{repo}` ({existing})."
    return None


def write_workspace_config(workspace_config_file: Path, payload: dict[str, object]) -> None:
    workspace_config_file.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def ensure_project_directory(path: Path, *, use_existing: bool, rel: Callable[[Path], str]) -> None:
    if path.exists():
        if not path.is_dir():
            raise SystemExit(f"{rel(path)} existe pero no es un directorio.")
        if any(path.iterdir()) and not use_existing:
            raise SystemExit(
                f"{rel(path)} ya existe y no esta vacio. Usa `--use-existing-dir` si quieres registrarlo igual."
            )
        return
    path.mkdir(parents=True, exist_ok=True)


def command_add_project(
    args,
    *,
    require_dirs: Callable[[], None],
    root: Path,
    root_repo: str,
    workspace_config: dict[str, object],
    workspace_config_file: Path,
    skills_config_file: Path,
    repo_config: dict[str, dict[str, object]],
    implementation_repos: Callable[[], list[str]],
    slugify: Callable[[str], str],
    rel: Callable[[Path], str],
    resolve_runtime_pack,
    load_skills_config,
    skills_entries,
    repo_placeholder_text,
    add_service_to_compose,
    runtime_catalog_error_type,
) -> int:
    require_dirs()
    repo_name = validate_identifier(args.name, "nombre del proyecto")
    if repo_name in repo_config:
        raise SystemExit(f"El proyecto `{repo_name}` ya existe en {workspace_config_file.name}.")

    repo_path = normalize_repo_path(args.path or repo_name)
    path_conflict = repo_path_conflicts(repo_path, repo_config=repo_config)
    if path_conflict:
        raise SystemExit(path_conflict)

    runtime = args.runtime
    try:
        defaults = resolve_runtime_pack(root, runtime, repo_name, repo_path)
    except runtime_catalog_error_type as exc:
        raise SystemExit(str(exc)) from exc

    target_roots = list(args.target_root or defaults["target_roots"])
    default_targets = list(args.default_target or defaults["default_targets"])
    test_runner = args.test_runner or str(defaults["test_runner"])
    test_hint = args.test_hint if args.test_hint is not None else defaults["test_hint"]
    if args.port is not None and not 1 <= args.port <= 65535:
        raise SystemExit("`--port` debe estar entre 1 y 65535.")
    compose_enabled = not args.no_compose and defaults["compose"] is not None
    service_name = validate_identifier(args.service_name or repo_name, "nombre del servicio")

    destination = root / repo_path
    ensure_project_directory(destination, use_existing=args.use_existing_dir, rel=rel)

    agents_text, readme_text = repo_placeholder_text(root_repo, repo_name, defaults["agent_skill_refs"])
    if not (destination / "AGENTS.md").exists():
        (destination / "AGENTS.md").write_text(agents_text, encoding="utf-8")
    if not (destination / "README.md").exists():
        (destination / "README.md").write_text(readme_text, encoding="utf-8")

    for directory in defaults["placeholder_dirs"]:
        target_dir = destination / directory
        target_dir.mkdir(parents=True, exist_ok=True)
        gitkeep = target_dir / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.write_text("", encoding="utf-8")

    for relative_path, content in defaults["placeholder_files"].items():
        target_file = destination / relative_path
        if not target_file.exists():
            target_file.write_text(content, encoding="utf-8")

    updated_config = json.loads(json.dumps(workspace_config))
    updated_config["repos"][repo_name] = {
        "path": repo_path,
        "compose_service": service_name if compose_enabled else repo_name,
        "kind": "implementation",
        "runtime": runtime,
        "repo_strategy": "plain",
        "slice_prefix": slugify(repo_name),
        "default_targets": default_targets,
        "target_roots": target_roots,
        "contract_roots": list(defaults["test_required_roots"]),
        "test_required_roots": list(defaults["test_required_roots"]),
        "agent_skill_refs": list(defaults["agent_skill_refs"]),
        "test_runner": test_runner,
    }
    if test_hint:
        updated_config["repos"][repo_name]["test_hint"] = test_hint
    write_workspace_config(workspace_config_file, updated_config)

    if compose_enabled:
        add_service_to_compose(service_name, repo_path, runtime, args.port, defaults["compose"])

    missing_skill_refs: list[str] = []
    try:
        skills_payload = load_skills_config()
        entries, errors = skills_entries(skills_payload)
        if errors:
            raise SystemExit("\n".join(f"- {error}" for error in errors))
        known_skill_refs = {str(entry["name"]) for entry in entries}
        missing_skill_refs = [ref for ref in defaults["agent_skill_refs"] if ref not in known_skill_refs]
    except SystemExit:
        missing_skill_refs = list(defaults["agent_skill_refs"])

    print(f"Proyecto agregado: {repo_name}")
    print(f"- path: {repo_path}")
    print(f"- runtime: {runtime}")
    print(f"- runtime_source: {rel(Path(defaults['source']))}")
    print(f"- compose_service: {service_name if compose_enabled else 'skipped'}")
    print(f"- agent_skill_refs: {', '.join(defaults['agent_skill_refs']) if defaults['agent_skill_refs'] else 'none'}")
    print(f"- config: {workspace_config_file.name}")
    if missing_skill_refs:
        print(f"- warning: faltan skills referenciadas en {skills_config_file.name}: {', '.join(missing_skill_refs)}")
    return 0
