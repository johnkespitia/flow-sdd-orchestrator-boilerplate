from __future__ import annotations

import json
from typing import Callable, Optional


def command_doctor(
    args,
    *,
    detect_compose_context,
    bmad_command_prefix,
    runtimes_config_file,
    capabilities_config_file,
    available_runtime_names,
    runtime_catalog_error_type,
    root,
    workspace_config_file,
    stack_config_file,
    skills_config_file,
    providers_config_file,
    secrets_config_file,
    specs_root,
    flow_root,
    repo_names: list[str],
    repo_root,
    slugify: Callable[[str], str],
    worktree_root,
    workspace_path: str,
    compose_control_root,
    running_inside_workspace: Callable[[], bool],
    shutil_which,
    project_name: str,
    json_dumps: Callable[[object], str],
) -> int:
    stack_context = detect_compose_context()
    bmad_available = False
    bmad_command = "unresolved"
    runtime_catalog_error: Optional[str] = None
    runtime_names: list[str] = []
    try:
        prefix = bmad_command_prefix()
        bmad_available = True
        bmad_command = " ".join(prefix)
    except SystemExit:
        pass

    runtime_manifest_ok = runtimes_config_file.is_file()
    if runtime_manifest_ok:
        try:
            runtime_names = available_runtime_names(root)
        except runtime_catalog_error_type as exc:
            runtime_catalog_error = str(exc)
            runtime_manifest_ok = False

    checks: dict[str, bool] = {
        "devcontainer": root.joinpath(".devcontainer").is_dir(),
        "tessl_root": root.joinpath(".tessl").is_dir(),
        "tessl_json": root.joinpath("tessl.json").is_file(),
        "workspace_config": workspace_config_file.is_file(),
        "capabilities_manifest": capabilities_config_file.is_file(),
        "skills_manifest": skills_config_file.is_file(),
        "runtimes_manifest": runtime_manifest_ok,
        "providers_manifest": providers_config_file.is_file(),
        "secrets_manifest": secrets_config_file.is_file(),
        "stack_manifest": stack_config_file.is_file(),
        "specs_root": specs_root.is_dir(),
        "flow_state": flow_root.is_dir(),
        "templates": root.joinpath("templates").is_dir(),
        "docker_cli": shutil_which("docker") is not None,
    }
    for repo in repo_names:
        checks[f"repo_{slugify(repo).replace('-', '_')}"] = repo_root(repo).is_dir()

    payload = {
        "project": project_name,
        "checks": checks,
        "workspace_root": str(root),
        "worktree_root": str(worktree_root),
        "workspace_mount_path": workspace_path,
        "compose_control_root": str(compose_control_root().resolve()),
        "compose_project": stack_context["project"],
        "compose_active": bool(stack_context["active"]),
        "runtime_names": runtime_names,
        "runtime_catalog_error": runtime_catalog_error,
        "bmad_available": bmad_available,
        "bmad_command": bmad_command,
        "bmad_project": root.joinpath("_bmad").is_dir(),
        "tessl_runtime_local": bool(shutil_which("tessl")) if running_inside_workspace() else None,
    }

    missing_test_roots: list[str] = []
    try:
        workspace_payload = json.loads(workspace_config_file.read_text(encoding="utf-8"))
        repos_payload = workspace_payload.get("repos", {})
        if isinstance(repos_payload, dict):
            for repo_name, repo_cfg in repos_payload.items():
                if not isinstance(repo_cfg, dict):
                    continue
                if str(repo_cfg.get("kind", "")).strip().lower() == "root":
                    continue
                target_roots_raw = repo_cfg.get("target_roots", [])
                target_roots = [
                    str(item).strip().strip("/")
                    for item in (target_roots_raw if isinstance(target_roots_raw, list) else [])
                    if str(item).strip().strip("/")
                ]
                has_test_root = any(
                    root == "tests" or root.endswith("/tests")
                    for root in target_roots
                )
                if not has_test_root:
                    missing_test_roots.append(str(repo_name))
    except Exception:
        # doctor keeps running; this is only an advisory governance signal.
        pass

    if missing_test_roots:
        payload["missing_test_roots"] = missing_test_roots
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
        missing = [name for name, ok in checks.items() if not ok]
        return 1 if missing else 0

    print(f"{project_name} flow doctor")
    for key, ok in checks.items():
        print(f"- {key}: {'ok' if ok else 'missing'}")

    missing = [name for name, ok in checks.items() if not ok]
    if missing:
        import sys

        print(f"\nFaltan rutas requeridas: {', '.join(missing)}", file=sys.stderr)
        return 1

    if missing_test_roots:
        print(f"\nWarning: repos sin root de tests en workspace.config.json: {', '.join(missing_test_roots)}")

    print(f"\nWorkspace root: {root}")
    print(f"Worktree root sugerido: {worktree_root}")
    print(f"Workspace mount path: {workspace_path}")
    print(f"Compose control root: {compose_control_root().resolve()}")
    print(f"Compose project: {stack_context['project']}")
    print(f"Compose activo: {'yes' if stack_context['active'] else 'no'}")
    print(f"BMAD CLI: {'ok' if bmad_available else 'missing'}")
    print(f"BMAD command: {bmad_command}")
    print(f"BMAD project: {'ok' if root.joinpath('_bmad').is_dir() else 'missing'}")
    if running_inside_workspace():
        print(f"Tessl runtime local: {'ok' if shutil_which('tessl') else 'missing'}")
    return 0
