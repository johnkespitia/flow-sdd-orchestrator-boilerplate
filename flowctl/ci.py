from __future__ import annotations

import json
import os
import shlex
import shutil
import textwrap
import time
from pathlib import Path
from typing import Callable, Optional

from flowctl.secret_scan import is_advisory_secret_finding
from flowctl.specs import frontmatter_status_allows_strict_ci, slice_governance_findings, verification_matrix_findings


def _normalize_relative_repo_paths(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        candidate = str(value).strip().replace("\\", "/").lstrip("./")
        if candidate:
            normalized.append(candidate)
    return normalized


def _repo_install_contract(repo_payload: dict[str, object], repo_path: Path) -> dict[str, object]:
    ci_payload = repo_payload.get("ci", {})
    if not isinstance(ci_payload, dict):
        ci_payload = {}
    install_contract = ci_payload.get("install_contract", {})
    if not isinstance(install_contract, dict):
        install_contract = {}

    test_runner = str(repo_payload.get("test_runner", "")).strip().lower()
    manifest_files: list[str] = []
    lock_files: list[str] = []
    strict_required = False

    if test_runner == "pnpm" or (repo_path / "package.json").exists():
        manifest_files = ["package.json"]
        lock_files = ["pnpm-lock.yaml", "package-lock.json", "yarn.lock"]
        strict_required = True
    elif test_runner == "php" or (repo_path / "composer.json").exists():
        manifest_files = ["composer.json"]
        lock_files = ["composer.lock"]
        strict_required = True
    elif test_runner == "go" or (repo_path / "go.mod").exists():
        manifest_files = ["go.mod"]
        lock_files = ["go.sum"]
        strict_required = True
    elif test_runner == "pytest" or (repo_path / "pyproject.toml").exists() or (repo_path / "requirements.txt").exists():
        manifest_files = ["pyproject.toml", "requirements.txt"]
        lock_files = ["poetry.lock", "uv.lock", "requirements.txt"]
        strict_required = True

    configured_manifests = install_contract.get("manifest_files")
    if isinstance(configured_manifests, list):
        manifest_files = [str(item) for item in configured_manifests if str(item).strip()]
    configured_locks = install_contract.get("lock_files")
    if isinstance(configured_locks, list):
        lock_files = [str(item) for item in configured_locks if str(item).strip()]

    mode = str(install_contract.get("mode", "")).strip().lower()
    if not mode:
        mode = "strict" if strict_required else "best_effort"

    return {
        "required": bool(manifest_files or lock_files),
        "mode": mode,
        "manifest_files": _normalize_relative_repo_paths(manifest_files),
        "lock_files": _normalize_relative_repo_paths(lock_files),
    }


def _command_has_strict_install_signal(command: list[str]) -> bool:
    joined = " ".join(str(part).strip().lower() for part in command if str(part).strip())
    if not joined:
        return False
    return any(
        token in joined
        for token in (
            "npm ci",
            "--frozen-lockfile",
            "composer install",
            "go mod download",
            "poetry install --sync",
            "uv sync",
            "pip-sync",
        )
    )


def _reproducible_install_findings(
    *,
    repo_name: str,
    repo_path: Path,
    repo_payload: dict[str, object],
    changed_files: list[str],
    commands: list[tuple[str, list[str]]],
) -> list[str]:
    contract = _repo_install_contract(repo_payload, repo_path)
    if not bool(contract.get("required")):
        return []

    manifest_files = [repo_path / item for item in contract.get("manifest_files", []) if isinstance(item, str)]
    lock_files = [repo_path / item for item in contract.get("lock_files", []) if isinstance(item, str)]
    manifest_exists = any(path.exists() for path in manifest_files)
    existing_lock_paths = [path for path in lock_files if path.exists()]
    mode = str(contract.get("mode", "best_effort")).strip().lower()

    findings: list[str] = []
    if manifest_exists and not existing_lock_paths:
        findings.append(
            f"`{repo_name}` declara install reproducible pero no tiene lockfile versionado ({', '.join(path.name for path in lock_files)})."
        )

    normalized_changed = _normalize_relative_repo_paths(changed_files)
    manifest_changed = any(str(path.relative_to(repo_path)).replace("\\", "/") in normalized_changed for path in manifest_files if path.exists())
    lock_changed = any(str(path.relative_to(repo_path)).replace("\\", "/") in normalized_changed for path in lock_files if path.exists())
    if manifest_changed and existing_lock_paths and not lock_changed:
        findings.append(
            f"`{repo_name}` cambio manifest de dependencias sin actualizar lockfile."
        )

    if mode == "strict":
        install_commands = [command for label, command in commands if label == "Install"]
        if install_commands and not any(_command_has_strict_install_signal(command) for command in install_commands):
            findings.append(
                f"`{repo_name}` declara install reproducible estricto pero su comando de instalacion CI no es estricto."
            )

    return findings


def load_ci_service_overrides_from_env() -> dict[str, dict[str, object]]:
    """JSON en FLOW_CI_SERVICE_OVERRIDES: { \"servicio\": { \"smoke_attempts\": 5, ... } }."""
    raw = os.environ.get("FLOW_CI_SERVICE_OVERRIDES", "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, object]] = {}
    for k, v in data.items():
        if isinstance(v, dict):
            out[str(k)] = v
    return out


def integration_profile_is_ci_clean(profile: str) -> bool:
    p = str(profile or "").strip().lower()
    return p in {"smoke:ci-clean", "smoke-ci-clean", "ci-clean"}


def resolve_ci_strict_preflight(profile: str, *, preflight_relaxed: bool) -> bool:
    return integration_profile_is_ci_clean(profile) and not preflight_relaxed


def merge_service_integration_settings(
    service_name: str,
    overrides: dict[str, dict[str, object]],
    *,
    default_attempts: int,
    default_backoff: float,
    default_health_timeout: int,
    default_health_poll: int,
) -> dict[str, float | int]:
    raw = overrides.get(service_name, {})

    def _int(key: str, default: int) -> int:
        if key not in raw:
            return default
        try:
            return int(raw[key])  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default

    def _float(key: str, default: float) -> float:
        if key not in raw:
            return default
        try:
            return float(raw[key])  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default

    return {
        "smoke_attempts": max(1, _int("smoke_attempts", default_attempts)),
        "smoke_backoff_seconds": max(0.0, _float("smoke_backoff_seconds", default_backoff)),
        "health_timeout_seconds": max(1, _int("health_timeout_seconds", default_health_timeout)),
        "health_poll_seconds": max(1, _int("health_poll_seconds", default_health_poll)),
    }


def command_ci_spec(
    args,
    *,
    require_dirs: Callable[[], None],
    select_spec_paths,
    analyze_spec,
    test_reference_findings,
    repos_missing_test_refs,
    spec_dependency_findings,
    rel: Callable[[Path], str],
    format_findings,
    slugify: Callable[[str], str],
    write_json,
    ci_report_root: Path,
    utc_now: Callable[[], str],
    json_dumps: Callable[[object], str],
) -> int:
    require_dirs()
    spec_paths = select_spec_paths(
        args.spec,
        all_specs=args.all,
        changed=args.changed,
        base=args.base,
        head=args.head,
    )
    if not spec_paths:
        print("No hay specs seleccionadas para CI.")
        return 0

    failures = 0
    items: list[dict[str, object]] = []
    report_lines = [
        "# CI Spec Governance",
        "",
        f"- Scope: `{args.spec or ('changed' if args.changed else 'all')}`",
        f"- Base: `{args.base or 'n/a'}`",
        f"- Head: `{args.head or 'n/a'}`",
        "",
    ]

    for spec_path in spec_paths:
        analysis = analyze_spec(spec_path)
        frontmatter = analysis["frontmatter"]
        status = str(frontmatter.get("status", "")).strip().lower()
        if (bool(getattr(args, "all", False)) or bool(getattr(args, "changed", False))) and not frontmatter_status_allows_strict_ci(status):
            advisory = (
                "Spec omitida en `ci spec` (modo `--all` o `--changed`) por estado no listo para CI estricto. "
                "Usa `flow spec review` + `flow spec approve` para incluirla en validacion estricta."
            )
            items.append(
                {
                    "spec": rel(spec_path),
                    "status": "skipped",
                    "frontmatter_status": frontmatter.get("status", ""),
                    "schema_version": analysis["schema_version"],
                    "repos": list(analysis["target_index"]),
                    "findings": [advisory],
                }
            )
            report_lines.append(f"## {rel(spec_path)}")
            report_lines.append("")
            report_lines.append("- Resultado: `skipped`")
            report_lines.append(f"- Estado frontmatter: `{frontmatter.get('status', 'missing')}`")
            report_lines.append("")
            report_lines.extend(format_findings([advisory]))
            report_lines.append("")
            continue
        findings: list[str] = []

        findings.extend(str(error) for error in analysis["frontmatter_errors"])
        for field in analysis["missing_frontmatter"]:
            findings.append(f"Falta el campo `{field}`.")
        findings.extend(str(error) for error in analysis["target_errors"])
        findings.extend(str(error) for error in analysis["test_errors"])
        findings.extend(spec_dependency_findings(analysis))
        findings.extend(test_reference_findings(analysis))
        findings.extend(slice_governance_findings(analysis))
        findings.extend(verification_matrix_findings(analysis))
        if analysis["todo_count"]:
            findings.append("La spec contiene `TODO`.")
        is_non_approved = not frontmatter_status_allows_strict_ci(status)
        non_blocking_draft = False
        if is_non_approved:
            message = (
                "La spec debe estar en estado `approved` o `released` para pasar CI. "
                "Si aun esta en `draft`, usa `flow spec review` para validarla y `flow spec approve` antes de correr este gate."
            )
            if non_blocking_draft:
                findings.append(f"(advisory) {message}")
            else:
                findings.append(message)

        missing_repo_tests = repos_missing_test_refs(analysis["target_index"], analysis["test_index"])
        if missing_repo_tests:
            findings.append(
                "Faltan referencias `[@test]` para: " + ", ".join(sorted(missing_repo_tests)) + "."
            )

        blocking_findings = [item for item in findings if not str(item).startswith("(advisory) ")]
        passed = not blocking_findings
        failures += 0 if passed else 1
        items.append(
            {
                "spec": rel(spec_path),
                "status": "passed" if passed else "failed",
                "frontmatter_status": frontmatter.get("status", ""),
                "schema_version": analysis["schema_version"],
                "repos": list(analysis["target_index"]),
                "findings": findings,
            }
        )
        report_lines.append(f"## {rel(spec_path)}")
        report_lines.append("")
        report_lines.append(f"- Resultado: `{'passed' if passed else 'failed'}`")
        report_lines.append(f"- Estado frontmatter: `{frontmatter.get('status', 'missing')}`")
        report_lines.append("")
        report_lines.extend(format_findings(findings))
        report_lines.append("")

    report_key = slugify(args.spec or ("changed" if args.changed else "all")) or "all"
    json_path = ci_report_root / f"spec-{report_key}.json"
    md_path = ci_report_root / f"spec-{report_key}.md"
    payload = {
        "generated_at": utc_now(),
        "base": args.base,
        "head": args.head,
        "scope": args.spec or ("changed" if args.changed else "all"),
        "items": items,
    }
    write_json(json_path, payload)
    md_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    payload["markdown_report"] = rel(md_path)
    payload["json_report"] = rel(json_path)
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
        return 1 if failures else 0
    print(rel(json_path))
    print(rel(md_path))
    return 1 if failures else 0


def command_ci_repo(
    args,
    *,
    require_dirs: Callable[[], None],
    implementation_repos: Callable[[], list[str]],
    resolve_spec,
    analyze_spec,
    repo_root,
    repo_config,
    repo_ci_commands,
    git_diff_name_only,
    git_changed_files,
    tracked_repo_files,
    scan_secret_paths,
    capture_command,
    write_json,
    plan_root: Path,
    ci_report_root: Path,
    slugify: Callable[[str], str],
    rel: Callable[[Path], str],
    format_findings,
    utc_now: Callable[[], str],
    json_dumps: Callable[[object], str],
    running_inside_workspace: Callable[[], bool],
    repo_compose_service: Callable[[str], str],
    run_workspace_tool: Callable[[list[str], Optional[bool], Optional[str]], int],
    workspace_flow_workdir: Callable[[], str],
    runtime_path: Callable[[Path], Path],
    host_root_hint: Callable[[], str],
) -> int:
    require_dirs()
    if getattr(args, "all", False) and args.repo:
        raise SystemExit("Usa `flow ci repo --all` o `flow ci repo <repo>`, no ambos.")
    if not getattr(args, "all", False) and not args.repo:
        raise SystemExit("Debes indicar un repo o usar `--all`.")
    repo_names = implementation_repos() if getattr(args, "all", False) else [args.repo]

    if (
        not running_inside_workspace()
        and any(repo_compose_service(repo_name).strip() for repo_name in repo_names)
        and os.environ.get("FLOW_SKIP_WORKSPACE_DELEGATION") != "1"
        and os.environ.get("GITHUB_ACTIONS", "").lower() != "true"
        and os.environ.get("FLOW_DELEGATED_TO_WORKSPACE") != "1"
    ):
        delegated_command = [
            "env",
            "FLOW_DELEGATED_TO_WORKSPACE=1",
            f"FLOW_HOST_ROOT={host_root_hint()}",
            "python3",
            "./flow",
            "ci",
            "repo",
        ]
        if getattr(args, "all", False):
            delegated_command.append("--all")
        elif args.repo:
            delegated_command.append(str(args.repo))
        if args.spec:
            delegated_command.extend(["--spec", str(args.spec)])
        if args.base:
            delegated_command.extend(["--base", str(args.base)])
        if args.head:
            delegated_command.extend(["--head", str(args.head)])
        if getattr(args, "skip_install", False):
            delegated_command.append("--skip-install")
        if bool(getattr(args, "json", False)):
            delegated_command.append("--json")
        return run_workspace_tool(delegated_command, False, workspace_flow_workdir())

    analysis = analyze_spec(resolve_spec(args.spec)) if args.spec else None
    payloads: list[dict[str, object]] = []
    failed = False

    planned_paths: dict[str, Path] = {}
    if args.spec:
        plan_path = plan_root / f"{slugify(args.spec)}.json"
        if plan_path.exists():
            try:
                plan_payload = json.loads(plan_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                plan_payload = {}
            for slice_payload in plan_payload.get("slices", []):
                if not isinstance(slice_payload, dict):
                    continue
                repo_name = str(slice_payload.get("repo", "")).strip()
                worktree = slice_payload.get("worktree")
                if not repo_name or not isinstance(worktree, str):
                    continue
                candidate = runtime_path(Path(worktree))
                if candidate.exists():
                    planned_paths[repo_name] = candidate

    for repo_name in repo_names:
        repo_path = planned_paths.get(repo_name, runtime_path(repo_root(repo_name)))
        commands = repo_ci_commands(repo_name, repo_path, skip_install=args.skip_install)
        repo_payload = repo_config(repo_name)

        related_targets: list[str] = []
        if analysis is not None:
            related_targets = [item["raw"] for item in analysis["target_index"].get(repo_name, [])]

        changed_files: list[str] = []
        diff_error: Optional[str] = None
        if args.base or args.head:
            changed_files, diff_error = git_diff_name_only(repo_path, base=args.base, head=args.head)
        else:
            changed_files, diff_error = git_changed_files(repo_path)

        executions: list[dict[str, object]] = []
        findings: list[str] = []

        if diff_error:
            findings.append(f"No pude resolver diff del repo: {diff_error}")

        findings.extend(
            _reproducible_install_findings(
                repo_name=repo_name,
                repo_path=repo_path,
                repo_payload=repo_payload if isinstance(repo_payload, dict) else {},
                changed_files=changed_files,
                commands=commands,
            )
        )

        secret_scan_paths = list(changed_files)
        if not secret_scan_paths:
            tracked_files, tracked_error = tracked_repo_files(repo_path)
            if tracked_error:
                findings.append(f"No pude resolver archivos trackeados para secret scan: {tracked_error}")
            else:
                secret_scan_paths = tracked_files

        secret_findings = scan_secret_paths(repo_name, repo_path, secret_scan_paths)
        for secret_finding in secret_findings:
            findings.append(
                f"Secret scan en `{secret_finding['path']}`: {', '.join(secret_finding['findings'])}."
            )

        for label, command in commands:
            execution = capture_command(command, repo_path)
            execution["label"] = label
            executions.append(execution)
            if execution["returncode"] != 0:
                findings.append(f"`{label}` fallo en `{repo_name}`.")

        if not commands:
            findings.append(f"No hay comandos CI configurados o detectables para `{repo_name}`.")

        report_payload = {
            "generated_at": utc_now(),
            "repo": repo_name,
            "repo_path": str(repo_path),
            "spec": args.spec,
            "related_targets": related_targets,
            "changed_files": changed_files,
            "secret_scan": secret_findings,
            "executions": executions,
            "findings": findings,
        }
        json_path = ci_report_root / f"repo-{slugify(repo_name)}.json"
        md_path = ci_report_root / f"repo-{slugify(repo_name)}.md"
        write_json(json_path, report_payload)

        lines = [
            f"# CI Repo Report: {repo_name}",
            "",
            f"- Repo path: `{repo_path}`",
            f"- Spec: `{args.spec or 'n/a'}`",
            "",
            "## Related targets",
            "",
        ]
        lines.extend([f"- `{target}`" for target in related_targets] or ["- No especificados."])
        lines.extend(["", "## Changed files", ""])
        lines.extend([f"- `{path}`" for path in changed_files] or ["- Ninguno detectado."])
        lines.extend(["", "## Secret scan", ""])
        lines.extend(
            [f"- `{item['path']}`: {', '.join(item['findings'])}" for item in secret_findings]
            or ["- Sin hallazgos."]
        )
        lines.extend(["", "## Executions", ""])
        if executions:
            for execution in executions:
                lines.append(
                    f"- `{execution['label']}`: returncode `{execution['returncode']}` "
                    f"con `{ ' '.join(shlex.quote(part) for part in execution['command']) }`"
                )
                if execution["output_tail"]:
                    lines.extend(["", "```text", str(execution["output_tail"]), "```", ""])
        else:
            lines.append("- Ninguna.")
        lines.extend(["", "## Findings", ""])
        lines.extend(format_findings(findings))
        md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        report_payload["markdown_report"] = rel(md_path)
        report_payload["json_report"] = rel(json_path)
        payloads.append(report_payload)
        has_blocking_secret_findings = any(
            not is_advisory_secret_finding(str(finding))
            for item in secret_findings
            for finding in item.get("findings", [])
        )
        failed = failed or has_blocking_secret_findings or any(int(item["returncode"]) != 0 for item in executions)

    if bool(getattr(args, "json", False)):
        print(json_dumps({"reports": payloads}))
        return 1 if failed else 0

    for payload in payloads:
        print(payload["json_report"])
        print(payload["markdown_report"])
    return 1 if failed else 0


def command_ci_integration(
    args,
    *,
    require_dirs: Callable[[], None],
    ensure_devcontainer_env: Callable[[], int],
    capture_compose,
    detect_compose_context,
    run_compose,
    implementation_repos: Callable[[], list[str]],
    repo_config,
    repo_compose_service,
    compose_exec_args,
    workspace_service: str,
    rel: Callable[[Path], str],
    format_findings,
    slugify: Callable[[str], str],
    utc_now: Callable[[], str],
    ci_report_root: Path,
    json_dumps: Callable[[object], str],
) -> int:
    require_dirs()
    checks: list[tuple[str, str, str, str]] = []
    findings: list[str] = []
    root = Path.cwd().resolve()

    profile = str(getattr(args, "profile", "smoke") or "smoke").strip().lower()
    preflight_relaxed = bool(getattr(args, "preflight_relaxed", False))
    bootstrap_runtime = bool(getattr(args, "bootstrap_runtime", False))
    strict_preflight = resolve_ci_strict_preflight(profile, preflight_relaxed=preflight_relaxed)
    service_overrides = load_ci_service_overrides_from_env()

    stack_up_attempts = max(1, int(os.environ.get("FLOW_CI_STACK_UP_ATTEMPTS", "3")))
    stack_up_backoff_seconds = max(0.0, float(os.environ.get("FLOW_CI_STACK_UP_BACKOFF_SECONDS", "2")))
    smoke_attempts = max(1, int(os.environ.get("FLOW_CI_SMOKE_ATTEMPTS", "4")))
    smoke_retry_delay_seconds = max(0.0, float(os.environ.get("FLOW_CI_SMOKE_BACKOFF_SECONDS", "2")))
    health_wait_timeout_seconds = max(1, int(os.environ.get("FLOW_CI_HEALTH_TIMEOUT_SECONDS", "30")))
    health_wait_interval_seconds = max(1, int(os.environ.get("FLOW_CI_HEALTH_POLL_SECONDS", "2")))

    def add_check(status: str, category: str, name: str, detail: str) -> None:
        checks.append((status, category, name, detail))

    def _compose_ps_records() -> list[dict[str, object]] | None:
        ps_json = capture_compose(["ps", "--format", "json"])
        if int(ps_json.get("returncode", 1)) != 0:
            return None
        raw = str(ps_json.get("stdout", "")).strip()
        if not raw:
            return None
        try:
            payload = json.loads(raw)
            if isinstance(payload, list):
                return [item for item in payload if isinstance(item, dict)]
            if isinstance(payload, dict):
                return [payload]
        except json.JSONDecodeError:
            records: list[dict[str, object]] = []
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    records.append(item)
            if records:
                return records
        return None

    def _health_status(records: list[dict[str, object]] | None, service_name: str) -> str:
        if records is None:
            return "unknown"
        for item in records:
            service = str(item.get("Service", "") or item.get("Name", "")).strip()
            if service != service_name:
                continue
            health = str(item.get("Health", "")).strip().lower()
            if health:
                return health
            return "no-healthcheck"
        return "missing"

    def wait_for_healthy_if_declared(service_name: str, *, timeout_s: int, poll_s: int) -> tuple[bool, str]:
        deadline = time.time() + float(timeout_s)
        saw_healthcheck = False
        last = "unknown"
        while time.time() <= deadline:
            records = _compose_ps_records()
            current = _health_status(records, service_name)
            last = current
            if current in {"unknown", "missing"}:
                return True, current
            if current == "no-healthcheck":
                return True, current
            saw_healthcheck = True
            if current == "healthy":
                return True, "healthy"
            time.sleep(float(poll_s))
        if saw_healthcheck:
            return False, last
        return True, last

    if shutil.which("docker") is None:
        raise SystemExit("No encontre `docker` en PATH para ejecutar CI de integracion.")

    context = detect_compose_context()
    env_ready_for_compose = True
    if not context["active"] and args.auto_up:
        env_rc = ensure_devcontainer_env()
        if env_rc != 0:
            env_ready_for_compose = False
            findings.append("No pude materializar `.devcontainer/.env.generated` antes de validar Compose.")
            add_check("FAIL", "infra", "Secrets bootstrap", "No se pudo generar el entorno del devcontainer.")
        else:
            add_check("PASS", "infra", "Secrets bootstrap", "El entorno del devcontainer esta listo para Compose.")

    config_check = capture_compose(["config", "--quiet"])
    if int(config_check["returncode"]) == 0:
        add_check("PASS", "infra", "Compose config", "La configuracion Compose es valida.")
    else:
        add_check("FAIL", "infra", "Compose config", "La configuracion Compose no pudo validarse.")
        findings.append("`docker compose config --quiet` fallo.")

    if not context["active"] and args.auto_up and env_ready_for_compose:
        up_args = ["up", "-d"]
        if args.build:
            up_args.append("--build")
        up_rc = 1
        attempts_used = 0
        for attempt in range(1, stack_up_attempts + 1):
            attempts_used = attempt
            up_rc = run_compose(up_args)
            if up_rc == 0:
                break
            if attempt < stack_up_attempts:
                time.sleep(stack_up_backoff_seconds)
        context = detect_compose_context()
        if up_rc != 0:
            ps_tail = str(capture_compose(["ps"]).get("output_tail", "")).strip()
            findings.append(
                f"No pude levantar el stack para la smoke suite tras {attempts_used} intentos."
            )
            if ps_tail:
                findings.append(f"Diagnostico stack bootstrap (tail): {ps_tail}")
            add_check(
                "FAIL",
                "infra",
                "Stack bootstrap",
                f"El stack no pudo arrancar tras {attempts_used} intentos.",
            )
        elif context["active"]:
            if attempts_used == 1:
                add_check("PASS", "infra", "Stack bootstrap", "El stack se levanto para ejecutar la smoke suite.")
            else:
                add_check(
                    "PASS",
                    "infra",
                    "Stack bootstrap",
                    f"El stack se levanto tras {attempts_used} intentos.",
                )

    if context["active"]:
        ps_check = capture_compose(["ps"])
        if int(ps_check["returncode"]) == 0:
            add_check("PASS", "infra", "Stack status", "Se pudo inspeccionar el estado de los servicios.")
        else:
            findings.append("`docker compose ps` fallo durante la smoke suite.")
            add_check("FAIL", "infra", "Stack status", "No se pudo inspeccionar el stack.")

        services_check = capture_compose(["config", "--services"])
        service_names = [line.strip() for line in str(services_check["stdout"]).splitlines() if line.strip()]

        smoke_commands = {
            workspace_service: ["sh", "-lc", "tessl --help >/dev/null && bmad --help >/dev/null"],
            "db": ["sh", "-lc", "mysqladmin ping -h localhost -u root -proot >/dev/null"],
            "postgres": ["sh", "-lc", "pg_isready -U app -d app_dev >/dev/null"],
            "mongo": ["sh", "-lc", "mongosh --quiet --eval 'db.runCommand({ ping: 1 })' >/dev/null"],
        }
        for repo in implementation_repos():
            runner = str(repo_config(repo).get("test_runner", "")).strip()
            service_name = repo_compose_service(repo)
            if runner == "php":
                smoke_commands[service_name] = ["sh", "-lc", "php --version >/dev/null"]
            elif runner == "pnpm":
                smoke_commands[service_name] = ["sh", "-lc", "node --version >/dev/null && pnpm --version >/dev/null"]
            elif runner == "go":
                smoke_commands[service_name] = ["go", "version"]

        container_root = os.environ.get("FLOW_WORKSPACE_CONTAINER_PATH", "/workspace").strip() or "/workspace"
        if bootstrap_runtime:
            for repo in implementation_repos():
                service_name = repo_compose_service(repo)
                if service_name not in service_names:
                    continue
                runner = str(repo_config(repo).get("test_runner", "")).strip()
                repo_path_raw = str(repo_config(repo).get("path", ".")).strip() or "."
                repo_path = Path(repo_path_raw)
                if not repo_path.is_absolute():
                    repo_path = (root / repo_path).resolve()
                try:
                    rel_posix = repo_path.relative_to(root).as_posix()
                except ValueError:
                    findings.append(f"(bootstrap) Path de repo `{repo}` fuera del workspace; omitido.")
                    continue
                cwd = f"{container_root}/{rel_posix}".replace("//", "/")
                if runner == "php" and (repo_path / "composer.json").exists():
                    bc = capture_compose(
                        compose_exec_args(service_name, interactive=False, workdir=cwd)
                        + ["composer", "install", "--no-interaction", "--no-progress"]
                    )
                    if int(bc["returncode"]) != 0:
                        findings.append(f"Bootstrap composer fallo en `{service_name}`.")
                        add_check("FAIL", "app", f"Bootstrap {service_name}", "`composer install` fallo.")
                    else:
                        add_check("PASS", "app", f"Bootstrap {service_name}", "`composer install` ok.")
                elif runner == "pnpm" and (repo_path / "package.json").exists():
                    bc = capture_compose(
                        compose_exec_args(service_name, interactive=False, workdir=cwd)
                        + ["sh", "-lc", "pnpm install --frozen-lockfile 2>/dev/null || pnpm install"]
                    )
                    if int(bc["returncode"]) != 0:
                        findings.append(f"Bootstrap pnpm fallo en `{service_name}`.")
                        add_check("FAIL", "app", f"Bootstrap {service_name}", "`pnpm install` fallo.")
                    else:
                        add_check("PASS", "app", f"Bootstrap {service_name}", "`pnpm install` ok.")

        for repo in implementation_repos():
            runner = str(repo_config(repo).get("test_runner", "")).strip()
            service_name = repo_compose_service(repo)
            repo_path_raw = str(repo_config(repo).get("path", ".")).strip() or "."
            repo_path = Path(repo_path_raw)
            if not repo_path.is_absolute():
                repo_path = (root / repo_path).resolve()
            preflight_issues: list[str] = []
            if runner == "php":
                composer_json = repo_path / "composer.json"
                autoload = repo_path / "vendor" / "autoload.php"
                if composer_json.exists() and not autoload.exists():
                    preflight_issues.append("falta `vendor/autoload.php`")
            elif runner == "pnpm":
                package_json = repo_path / "package.json"
                has_lock = any((repo_path / name).exists() for name in ("pnpm-lock.yaml", "package-lock.json", "yarn.lock"))
                node_modules = repo_path / "node_modules"
                if package_json.exists() and not has_lock:
                    preflight_issues.append("falta lockfile (`pnpm-lock.yaml`/`package-lock.json`/`yarn.lock`)")
                if package_json.exists() and not node_modules.exists():
                    preflight_issues.append("falta `node_modules/`")
            if preflight_issues:
                detail = f"Preflight `{service_name}`: " + ", ".join(preflight_issues)
                if strict_preflight:
                    findings.append(detail)
                    add_check("FAIL", "app", f"Preflight {service_name}", "Prerequisitos de runtime incompletos.")
                else:
                    findings.append(f"(advisory) {detail}")
                    add_check("WARN", "app", f"Preflight {service_name}", "Prerequisitos incompletos (advisory).")

        for service_name, smoke_command in smoke_commands.items():
            if service_name not in service_names:
                continue

            svc = merge_service_integration_settings(
                service_name,
                service_overrides,
                default_attempts=smoke_attempts,
                default_backoff=smoke_retry_delay_seconds,
                default_health_timeout=health_wait_timeout_seconds,
                default_health_poll=health_wait_interval_seconds,
            )
            svc_attempts = int(svc["smoke_attempts"])
            svc_backoff = float(svc["smoke_backoff_seconds"])
            svc_health_timeout = int(svc["health_timeout_seconds"])
            svc_health_poll = int(svc["health_poll_seconds"])

            health_ok, health_state = wait_for_healthy_if_declared(
                service_name, timeout_s=svc_health_timeout, poll_s=svc_health_poll
            )
            if not health_ok:
                findings.append(
                    f"El servicio `{service_name}` no llego a healthy en {svc_health_timeout}s (estado: {health_state})."
                )
                add_check(
                    "FAIL",
                    "infra",
                    f"Health {service_name}",
                    f"No llego a healthy en {svc_health_timeout}s (estado: {health_state}).",
                )
                continue

            attempt = 0
            last_execution: dict[str, object] = {}
            while attempt < svc_attempts:
                attempt += 1
                last_execution = capture_compose(compose_exec_args(service_name, interactive=False) + smoke_command)
                if int(last_execution["returncode"]) == 0:
                    break
                if attempt < svc_attempts:
                    time.sleep(svc_backoff)

            if int(last_execution.get("returncode", 1)) == 0:
                if attempt == 1:
                    add_check("PASS", "app", f"Smoke {service_name}", f"El servicio `{service_name}` respondio al smoke check.")
                else:
                    add_check(
                        "PASS",
                        "app",
                        f"Smoke {service_name}",
                        f"El servicio `{service_name}` respondio al smoke check tras {attempt} intentos.",
                    )
            else:
                tail = str(last_execution.get("output_tail", "")).strip()
                findings.append(
                    f"El smoke check de `{service_name}` fallo tras {svc_attempts} intentos."
                )
                if tail:
                    findings.append(f"Diagnostico smoke `{service_name}` (tail): {tail}")
                add_check(
                    "FAIL",
                    "app",
                    f"Smoke {service_name}",
                    f"El comando del smoke check devolvio error tras {svc_attempts} intentos.",
                )
    else:
        findings.append("El stack no esta activo; usa `--auto-up` o levanta Compose antes de integrar.")
        add_check("FAIL", "infra", "Stack active", "No hay proyecto Compose activo para la smoke suite.")

    report_path = ci_report_root / f"integration-{slugify(args.profile)}.md"
    report = textwrap.dedent(
        f"""\
        # CI Integration Report

        - Profile: `{args.profile}`
        - Generated at: `{utc_now()}`

        ## Checks

        {chr(10).join(f"- [{status}][{category}] **{name}**: {detail}" for status, category, name, detail in checks)}

        ## Findings

        {chr(10).join(format_findings(findings))}
        """
    )
    report_path.write_text(report, encoding="utf-8")
    payload = {
        "generated_at": utc_now(),
        "profile": args.profile,
        "contract": {
            "ci_clean_profile": integration_profile_is_ci_clean(profile),
            "strict_preflight": strict_preflight,
            "preflight_relaxed": preflight_relaxed,
            "bootstrap_runtime": bootstrap_runtime,
            "service_overrides_keys": sorted(service_overrides.keys()),
        },
        "checks": [
            {"status": status, "category": category, "name": name, "detail": detail}
            for status, category, name, detail in checks
        ],
        "findings": findings,
        "markdown_report": rel(report_path),
    }
    failed = any(status == "FAIL" for status, _, _, _ in checks)
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
        return 1 if failed else 0
    print(rel(report_path))
    return 1 if failed else 0
