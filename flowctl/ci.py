from __future__ import annotations

import json
import os
import shlex
import shutil
import textwrap
from pathlib import Path
from typing import Callable, Optional

from flowctl.secret_scan import is_advisory_secret_finding


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
        findings: list[str] = []

        findings.extend(str(error) for error in analysis["frontmatter_errors"])
        for field in analysis["missing_frontmatter"]:
            findings.append(f"Falta el campo `{field}`.")
        findings.extend(str(error) for error in analysis["target_errors"])
        findings.extend(str(error) for error in analysis["test_errors"])
        findings.extend(spec_dependency_findings(analysis))
        findings.extend(test_reference_findings(analysis))
        if analysis["todo_count"]:
            findings.append("La spec contiene `TODO`.")
        if frontmatter.get("status") != "approved":
            findings.append(
                "La spec debe estar en estado `approved` para pasar CI. "
                "Si aun esta en `draft`, usa `flow spec review` para validarla y `flow spec approve` antes de correr este gate."
            )

        missing_repo_tests = repos_missing_test_refs(analysis["target_index"], analysis["test_index"])
        if missing_repo_tests:
            findings.append(
                "Faltan referencias `[@test]` para: " + ", ".join(sorted(missing_repo_tests)) + "."
            )

        passed = not findings
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
    checks: list[tuple[str, str, str]] = []
    findings: list[str] = []

    if shutil.which("docker") is None:
        raise SystemExit("No encontre `docker` en PATH para ejecutar CI de integracion.")

    context = detect_compose_context()
    env_ready_for_compose = True
    if not context["active"] and args.auto_up:
        env_rc = ensure_devcontainer_env()
        if env_rc != 0:
            env_ready_for_compose = False
            findings.append("No pude materializar `.devcontainer/.env.generated` antes de validar Compose.")
            checks.append(("FAIL", "Secrets bootstrap", "No se pudo generar el entorno del devcontainer."))
        else:
            checks.append(("PASS", "Secrets bootstrap", "El entorno del devcontainer esta listo para Compose."))

    config_check = capture_compose(["config", "--quiet"])
    if int(config_check["returncode"]) == 0:
        checks.append(("PASS", "Compose config", "La configuracion Compose es valida."))
    else:
        checks.append(("FAIL", "Compose config", "La configuracion Compose no pudo validarse."))
        findings.append("`docker compose config --quiet` fallo.")

    if not context["active"] and args.auto_up and env_ready_for_compose:
        up_args = ["up", "-d"]
        if args.build:
            up_args.append("--build")
        up_rc = run_compose(up_args)
        context = detect_compose_context()
        if up_rc != 0:
            findings.append("No pude levantar el stack para la smoke suite.")
            checks.append(("FAIL", "Stack bootstrap", "El stack no pudo arrancar."))
        elif context["active"]:
            checks.append(("PASS", "Stack bootstrap", "El stack se levanto para ejecutar la smoke suite."))

    if context["active"]:
        ps_check = capture_compose(["ps"])
        if int(ps_check["returncode"]) == 0:
            checks.append(("PASS", "Stack status", "Se pudo inspeccionar el estado de los servicios."))
        else:
            findings.append("`docker compose ps` fallo durante la smoke suite.")
            checks.append(("FAIL", "Stack status", "No se pudo inspeccionar el stack."))

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
        for service_name, smoke_command in smoke_commands.items():
            if service_name not in service_names:
                continue
            execution = capture_compose(compose_exec_args(service_name, interactive=False) + smoke_command)
            if int(execution["returncode"]) == 0:
                checks.append(("PASS", f"Smoke {service_name}", f"El servicio `{service_name}` respondio al smoke check."))
            else:
                findings.append(f"El smoke check de `{service_name}` fallo.")
                checks.append(("FAIL", f"Smoke {service_name}", "El comando del smoke check devolvio error."))
    else:
        findings.append("El stack no esta activo; usa `--auto-up` o levanta Compose antes de integrar.")
        checks.append(("FAIL", "Stack active", "No hay proyecto Compose activo para la smoke suite."))

    report_path = ci_report_root / f"integration-{slugify(args.profile)}.md"
    report = textwrap.dedent(
        f"""\
        # CI Integration Report

        - Profile: `{args.profile}`
        - Generated at: `{utc_now()}`

        ## Checks

        {chr(10).join(f"- [{status}] **{name}**: {detail}" for status, name, detail in checks)}

        ## Findings

        {chr(10).join(format_findings(findings))}
        """
    )
    report_path.write_text(report, encoding="utf-8")
    payload = {
        "generated_at": utc_now(),
        "profile": args.profile,
        "checks": [{"status": status, "name": name, "detail": detail} for status, name, detail in checks],
        "findings": findings,
        "markdown_report": rel(report_path),
    }
    failed = any(status == "FAIL" for status, _, _ in checks)
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
        return 1 if failed else 0
    print(rel(report_path))
    return 1 if failed else 0
