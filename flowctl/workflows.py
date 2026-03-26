from __future__ import annotations

import contextlib
import io
import json
import os
import shlex
import textwrap
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable


def workflow_assets(root: Path) -> dict[str, Path]:
    return {
        "tessl_rules": root / ".tessl" / "RULES.md",
        "tessl_tile_dir": root / ".tessl" / "tiles" / "workspace" / "spec-driven-workspace",
        "tessl_tile_index": root / ".tessl" / "tiles" / "workspace" / "spec-driven-workspace" / "index.md",
        "tessl_tile_format": root / ".tessl" / "tiles" / "workspace" / "spec-driven-workspace" / "spec-format.md",
        "tessl_tile_styleguide": root / ".tessl" / "tiles" / "workspace" / "spec-driven-workspace" / "spec-styleguide.md",
        "tessl_tile_verification": root / ".tessl" / "tiles" / "workspace" / "spec-driven-workspace" / "spec-verification.md",
        "bmad_quick_spec": root / "_bmad" / "bmm" / "workflows" / "bmad-quick-flow" / "quick-spec" / "workflow.md",
        "bmad_quick_dev": root / "_bmad" / "bmm" / "workflows" / "bmad-quick-flow" / "quick-dev" / "workflow.md",
        "bmad_create_story": root / "_bmad" / "bmm" / "workflows" / "4-implementation" / "create-story" / "workflow.md",
        "bmad_dev_story": root / "_bmad" / "bmm" / "workflows" / "4-implementation" / "dev-story" / "workflow.md",
        "bmad_sprint_status": root / "_bmad" / "bmm" / "workflows" / "4-implementation" / "sprint-status" / "workflow.md",
    }


def flow_shell_command(parts: list[str]) -> str:
    return "python3 ./flow " + " ".join(shlex.quote(part) for part in parts)


def _truthy(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def workflow_orchestrator_settings(args, *, workspace_config: dict[str, object]) -> tuple[str, str, bool]:
    project = workspace_config.get("project", {}) if isinstance(workspace_config, dict) else {}
    workflow = project.get("workflow", {}) if isinstance(project, dict) else {}

    cli_orchestrator = str(getattr(args, "orchestrator", "") or "").strip().lower()
    env_orchestrator = str(os.environ.get("FLOW_WORKFLOW_ORCHESTRATOR", "")).strip().lower()
    cfg_orchestrator = str(workflow.get("default_orchestrator", "")).strip().lower() if isinstance(workflow, dict) else ""
    orchestrator = cli_orchestrator or env_orchestrator or cfg_orchestrator or "bmad"
    source = (
        "cli"
        if cli_orchestrator
        else "env"
        if env_orchestrator
        else "workspace.config.json"
        if cfg_orchestrator
        else "builtin-default"
    )

    force = bool(getattr(args, "force_orchestrator", False))
    if not force:
        force = _truthy(os.environ.get("FLOW_WORKFLOW_FORCE_ORCHESTRATOR", ""))
    if not force and isinstance(workflow, dict):
        force = bool(workflow.get("force_orchestrator", False))

    if orchestrator != "bmad":
        raise SystemExit(
            f"Orchestrator no soportado `{orchestrator}`. Por ahora solo se admite `bmad` "
            "(usa --orchestrator bmad o configura project.workflow.default_orchestrator=bmad)."
        )
    if force and orchestrator != "bmad":
        raise SystemExit("`--force-orchestrator` requiere `bmad`.")
    return orchestrator, source, force


def _doctor_payload(
    *,
    args,
    workspace_config: dict[str, object],
    root: Path,
    rel: Callable[[Path], str],
    capture_workspace_tool: Callable[[list[str]], dict[str, object]],
    bmad_command_prefix: Callable[[], list[str]],
    load_skills_config,
    skills_entries,
) -> dict[str, object]:
    assets = workflow_assets(root)
    findings: list[str] = []
    orchestrator, orchestrator_source, orchestrator_forced = workflow_orchestrator_settings(
        args,
        workspace_config=workspace_config,
    )

    payload = {
        "default_orchestrator": orchestrator,
        "orchestrator_source": orchestrator_source,
        "orchestrator_forced": orchestrator_forced,
        "default_spec_engine": "tessl",
        "assets": {name: {"path": rel(path), "exists": path.exists()} for name, path in assets.items()},
        "skills_manifest_ok": False,
        "tessl_runtime_ok": False,
        "tessl_tile_lint_ok": False,
        "tessl_help_tail": "",
        "tessl_tile_lint_tail": "",
        "bmad_runtime_ok": False,
        "bmad_status_tail": "",
        "bmad_command": "unresolved",
        "findings": findings,
    }

    missing_assets = [name for name, details in payload["assets"].items() if not details["exists"]]
    if missing_assets:
        findings.extend(f"Falta el asset requerido `{name}`." for name in missing_assets)

    skills_payload = load_skills_config()
    entries, errors = skills_entries(skills_payload)
    payload["skills_manifest_ok"] = not errors
    if errors:
        findings.extend(str(item) for item in errors)
    tile_entry_ok = any(
        isinstance(entry, dict)
        and str(entry.get("provider", "")).strip() == "tessl"
        and str(entry.get("name", "")).strip() == "workspace/spec-driven-workspace"
        and bool(entry.get("enabled", True))
        for entry in entries
    )
    if not tile_entry_ok:
        findings.append("`workspace.skills.json` no expone el tile Tessl `workspace/spec-driven-workspace` como entrypoint habilitado.")

    tessl_help = capture_workspace_tool(["tessl", "--help"])
    payload["tessl_help_tail"] = str(tessl_help.get("output_tail", ""))
    payload["tessl_runtime_ok"] = int(tessl_help.get("returncode", 1)) == 0
    if not payload["tessl_runtime_ok"]:
        findings.append("No pude ejecutar `tessl --help` dentro del workspace.")

    tessl_lint = capture_workspace_tool(["tessl", "tile", "lint", rel(assets["tessl_tile_dir"])])
    payload["tessl_tile_lint_tail"] = str(tessl_lint.get("output_tail", ""))
    payload["tessl_tile_lint_ok"] = int(tessl_lint.get("returncode", 1)) == 0
    if not payload["tessl_tile_lint_ok"]:
        findings.append("El tile Tessl local no pasa `tessl tile lint`.")

    try:
        command_prefix = bmad_command_prefix()
        payload["bmad_command"] = " ".join(command_prefix)
        bmad_status = capture_workspace_tool([*command_prefix, "status"])
        payload["bmad_status_tail"] = str(bmad_status.get("output_tail", ""))
        payload["bmad_runtime_ok"] = int(bmad_status.get("returncode", 1)) == 0
        if not payload["bmad_runtime_ok"]:
            findings.append("No pude ejecutar `bmad status` dentro del workspace.")
    except SystemExit as exc:
        findings.append(str(exc))

    return payload


def command_workflow_doctor(
    args,
    *,
    require_dirs: Callable[[], None],
    workspace_config: dict[str, object],
    root: Path,
    rel: Callable[[Path], str],
    capture_workspace_tool: Callable[[list[str]], dict[str, object]],
    bmad_command_prefix: Callable[[], list[str]],
    load_skills_config,
    skills_entries,
    json_dumps: Callable[[object], str],
) -> int:
    require_dirs()
    payload = _doctor_payload(
        args=args,
        workspace_config=workspace_config,
        root=root,
        rel=rel,
        capture_workspace_tool=capture_workspace_tool,
        bmad_command_prefix=bmad_command_prefix,
        load_skills_config=load_skills_config,
        skills_entries=skills_entries,
    )
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
        return 1 if payload["findings"] else 0

    print("Workflow doctor")
    print(f"- default orchestrator: {payload['default_orchestrator']}")
    print(f"- default spec engine: {payload['default_spec_engine']}")
    print(f"- tessl runtime: {'ok' if payload['tessl_runtime_ok'] else 'missing'}")
    print(f"- tessl tile lint: {'ok' if payload['tessl_tile_lint_ok'] else 'failed'}")
    print(f"- bmad runtime: {'ok' if payload['bmad_runtime_ok'] else 'missing'}")
    print(f"- bmad command: {payload['bmad_command']}")
    if payload["findings"]:
        import sys

        print("", file=sys.stderr)
        for finding in payload["findings"]:
            print(f"- {finding}", file=sys.stderr)
        return 1
    return 0


def command_workflow_intake(
    args,
    *,
    require_dirs: Callable[[], None],
    workspace_config: dict[str, object],
    root: Path,
    root_repo: str,
    feature_specs: Path,
    workflow_report_root: Path,
    state_path: Callable[[str], Path],
    spec_create_callable: Callable[[object], int],
    slugify: Callable[[str], str],
    rel: Callable[[Path], str],
    load_skills_config,
    skills_entries,
    capture_workspace_tool: Callable[[list[str]], dict[str, object]],
    bmad_command_prefix: Callable[[], list[str]],
    utc_now: Callable[[], str],
    json_dumps: Callable[[object], str],
) -> int:
    require_dirs()
    workflow_report_root.mkdir(parents=True, exist_ok=True)

    slug = slugify(args.slug)
    requested_repos = []
    for repo in list(getattr(args, "repo", []) or []):
        candidate = str(repo).strip()
        if not candidate:
            continue
        requested_repos.append(root_repo if candidate == "root" else candidate)
    spec_args = type("SpecCreateArgs", (), {})()
    spec_args.slug = slug
    spec_args.title = args.title
    spec_args.repo = requested_repos
    spec_args.runtime = list(getattr(args, "runtime", []) or [])
    spec_args.service = list(getattr(args, "service", []) or [])
    spec_args.capability = list(getattr(args, "capability", []) or [])
    spec_args.depends_on = list(getattr(args, "depends_on", []) or [])
    spec_args.description = str(getattr(args, "description", "") or "").strip()
    spec_args.acceptance_criteria = list(getattr(args, "acceptance_criteria", []) or [])

    spec_stdout = io.StringIO()
    with contextlib.redirect_stdout(spec_stdout):
        spec_rc = spec_create_callable(spec_args)
    if spec_rc != 0:
        return spec_rc

    spec_path = feature_specs / f"{slug}.spec.md"
    assets = workflow_assets(root)
    doctor = _doctor_payload(
        args=args,
        workspace_config=workspace_config,
        root=root,
        rel=rel,
        capture_workspace_tool=capture_workspace_tool,
        bmad_command_prefix=bmad_command_prefix,
        load_skills_config=load_skills_config,
        skills_entries=skills_entries,
    )

    orchestrator, orchestrator_source, orchestrator_forced = workflow_orchestrator_settings(
        args,
        workspace_config=workspace_config,
    )
    payload = {
        "feature": slug,
        "stage": "intake",
        "generated_at": utc_now(),
        "spec": rel(spec_path),
        "state": rel(state_path(slug)),
        "spec_create_output": [line for line in spec_stdout.getvalue().splitlines() if line.strip()],
        "default_orchestrator": orchestrator,
        "orchestrator_source": orchestrator_source,
        "orchestrator_forced": orchestrator_forced,
        "default_spec_engine": "tessl",
        "bmad_workflow": {
            "name": "quick-spec",
            "path": rel(assets["bmad_quick_spec"]),
        },
        "tessl_context": {
            "tile": "workspace/spec-driven-workspace",
            "rules": rel(assets["tessl_rules"]),
            "index": rel(assets["tessl_tile_index"]),
            "format": rel(assets["tessl_tile_format"]),
            "styleguide": rel(assets["tessl_tile_styleguide"]),
            "verification": rel(assets["tessl_tile_verification"]),
        },
        "doctor": {
            "tessl_runtime_ok": doctor["tessl_runtime_ok"],
            "tessl_tile_lint_ok": doctor["tessl_tile_lint_ok"],
            "bmad_runtime_ok": doctor["bmad_runtime_ok"],
            "findings": list(doctor["findings"]),
        },
        "next_steps": [
            {
                "system": "tessl",
                "action": "read-tile",
                "path": rel(assets["tessl_tile_index"]),
            },
            {
                "system": "bmad",
                "action": "follow-workflow",
                "workflow": "quick-spec",
                "path": rel(assets["bmad_quick_spec"]),
            },
            {
                "system": "flow",
                "action": "review-spec",
                "command": flow_shell_command(["spec", "review", slug]),
            },
            {
                "system": "flow",
                "action": "inspect-next-step",
                "command": flow_shell_command(["workflow", "next-step", slug, "--json"]),
            },
        ],
    }

    json_path = workflow_report_root / f"{slug}-intake.json"
    md_path = workflow_report_root / f"{slug}-intake.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    md_path.write_text(
        textwrap.dedent(
            f"""\
            # Workflow Intake: {slug}

            - Spec: `{rel(spec_path)}`
            - State: `{rel(state_path(slug))}`
            - Default orchestrator: `{orchestrator}`
            - Default spec engine: `tessl`

            ## Tessl context

            - Tile: `workspace/spec-driven-workspace`
            - Rules: `{rel(assets['tessl_rules'])}`
            - Index: `{rel(assets['tessl_tile_index'])}`
            - Format: `{rel(assets['tessl_tile_format'])}`
            - Styleguide: `{rel(assets['tessl_tile_styleguide'])}`
            - Verification: `{rel(assets['tessl_tile_verification'])}`

            ## BMAD workflow

            - `quick-spec`: `{rel(assets['bmad_quick_spec'])}`

            ## Next flow commands

            - `{flow_shell_command(['spec', 'review', slug])}`
            - `{flow_shell_command(['workflow', 'next-step', slug, '--json'])}`
            """
        ),
        encoding="utf-8",
    )

    payload["json_report"] = rel(json_path)
    payload["markdown_report"] = rel(md_path)
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
        return 0
    print(rel(json_path))
    print(rel(md_path))
    return 0


def command_workflow_next_step(
    args,
    *,
    require_dirs: Callable[[], None],
    workspace_config: dict[str, object],
    resolve_spec: Callable[[str], Path],
    spec_slug: Callable[[Path], str],
    analyze_spec: Callable[[Path], dict[str, object]],
    read_state: Callable[[str], dict[str, object]],
    plan_root: Path,
    workflow_report_root: Path,
    root: Path,
    rel: Callable[[Path], str],
    utc_now: Callable[[], str],
    json_dumps: Callable[[object], str],
) -> int:
    require_dirs()
    workflow_report_root.mkdir(parents=True, exist_ok=True)
    orchestrator, orchestrator_source, orchestrator_forced = workflow_orchestrator_settings(
        args,
        workspace_config=workspace_config,
    )

    spec_path = resolve_spec(args.spec)
    slug = spec_slug(spec_path)
    analysis = analyze_spec(spec_path)
    frontmatter = analysis["frontmatter"]
    state = read_state(slug)
    assets = workflow_assets(root)
    plan_path = plan_root / f"{slug}.json"
    plan_payload = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.exists() else None
    slice_results = state.get("slice_results", {})
    if not isinstance(slice_results, dict):
        slice_results = {}

    stage = "spec-refinement"
    summary = "La spec aun debe cerrarse y revisarse con Tessl + BMAD quick-spec."
    next_commands: list[str] = [
        flow_shell_command(["spec", "review", slug]),
        flow_shell_command(["spec", "approve", slug, "--approver", "<id>"]),
    ]
    bmad_recommendation: dict[str, object] = {
        "name": "quick-spec",
        "path": rel(assets["bmad_quick_spec"]),
        "why": "La feature sigue en etapa de cierre de spec.",
    }
    subagents: list[dict[str, object]] = []

    if str(frontmatter.get("status", "draft")).strip() == "approved":
        if plan_payload is None:
            stage = "planning"
            summary = "La spec ya esta aprobada; el siguiente paso es derivar slices y worktrees."
            next_commands = [
                flow_shell_command(["plan", slug]),
                flow_shell_command(["workflow", "execute-feature", slug, "--start-slices", "--json"]),
            ]
            bmad_recommendation = {
                "name": "quick-dev",
                "path": rel(assets["bmad_quick_dev"]),
                "why": "La spec ya esta cerrada y puede pasar a implementacion guiada.",
            }
        else:
            pending_slices = []
            for slice_payload in plan_payload.get("slices", []):
                if not isinstance(slice_payload, dict):
                    continue
                name = str(slice_payload.get("name", "")).strip()
                result = slice_results.get(name, {})
                started = isinstance(result, dict) and str(result.get("status", "")).strip() == "started"
                pending_slices.append((slice_payload, started))
                subagents.append(
                    {
                        "slice": name,
                        "repo": str(slice_payload.get("repo", "")),
                        "branch": str(slice_payload.get("branch", "")),
                        "worktree": str(slice_payload.get("worktree", "")),
                        "started": started,
                        "recommended_workflow": "quick-dev",
                        "workflow_path": rel(assets["bmad_quick_dev"]),
                        "handoff": rel(workflow_report_root.parent / f"{slug}-{name}-handoff.md")
                        if (workflow_report_root.parent / f"{slug}-{name}-handoff.md").exists()
                        else None,
                    }
                )

            if any(not started for _, started in pending_slices):
                stage = "execution-ready"
                summary = "El plan existe; puedes arrancar slices por repo y asignarlas a subagentes."
                next_commands = [
                    flow_shell_command(["workflow", "execute-feature", slug, "--start-slices", "--json"]),
                ]
                next_commands.extend(
                    flow_shell_command(["slice", "start", slug, str(item.get("name", ""))])
                    for item, started in pending_slices
                    if isinstance(item, dict) and not started
                )
            else:
                stage = "verification"
                summary = "Las slices ya tienen worktrees; el siguiente paso es verificar cada slice y cerrar CI."
                next_commands = [
                    flow_shell_command(["slice", "verify", slug, str(item.get("name", "")), "--json"])
                    for item, _ in pending_slices
                    if isinstance(item, dict)
                ]
                next_commands.extend(
                    [
                        flow_shell_command(["ci", "spec", slug, "--json"]),
                        flow_shell_command(["ci", "repo", "--all", "--json"]),
                    ]
                )
            bmad_recommendation = {
                "name": "quick-dev",
                "path": rel(assets["bmad_quick_dev"]),
                "why": "Cada slice ya puede delegarse a un ejecutor con contexto cerrado.",
            }

    payload = {
        "feature": slug,
        "generated_at": utc_now(),
        "stage": stage,
        "summary": summary,
        "spec": rel(spec_path),
        "frontmatter_status": str(frontmatter.get("status", "draft")).strip() or "draft",
        "state_status": str(state.get("status", "idea")).strip() or "idea",
        "plan_exists": plan_path.exists(),
        "plan_path": rel(plan_path) if plan_path.exists() else None,
        "default_orchestrator": orchestrator,
        "orchestrator_source": orchestrator_source,
        "orchestrator_forced": orchestrator_forced,
        "default_spec_engine": "tessl",
        "bmad_recommendation": bmad_recommendation,
        "tessl_context": {
            "tile": "workspace/spec-driven-workspace",
            "index": rel(assets["tessl_tile_index"]),
            "verification": rel(assets["tessl_tile_verification"]),
        },
        "next_commands": next_commands,
        "subagents": subagents,
        "story_cycle": {
            "create_story": rel(assets["bmad_create_story"]),
            "dev_story": rel(assets["bmad_dev_story"]),
            "sprint_status": rel(assets["bmad_sprint_status"]),
        },
    }

    json_path = workflow_report_root / f"{slug}-next-step.json"
    md_path = workflow_report_root / f"{slug}-next-step.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    lines = [
        f"# Workflow Next Step: {slug}",
        "",
        f"- Stage: `{stage}`",
        f"- Spec: `{rel(spec_path)}`",
        f"- Frontmatter status: `{payload['frontmatter_status']}`",
        f"- State status: `{payload['state_status']}`",
        "",
        "## Summary",
        "",
        summary,
        "",
        "## Recommended BMAD workflow",
        "",
        f"- `{bmad_recommendation['name']}`: `{bmad_recommendation['path']}`",
        f"- Why: {bmad_recommendation['why']}",
        "",
        "## Next flow commands",
        "",
    ]
    lines.extend(f"- `{command}`" for command in next_commands)
    if subagents:
        lines.extend(
            [
                "",
                "## Suggested subagents",
                "",
            ]
        )
        for item in subagents:
            lines.append(
                f"- `{item['slice']}` -> repo=`{item['repo']}`, worktree=`{item['worktree']}`, "
                f"started={'yes' if item['started'] else 'no'}, workflow=`{item['workflow_path']}`"
            )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    payload["json_report"] = rel(json_path)
    payload["markdown_report"] = rel(md_path)
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
        return 0
    print(rel(json_path))
    print(rel(md_path))
    return 0


def command_workflow_execute_feature(
    args,
    *,
    require_dirs: Callable[[], None],
    workspace_config: dict[str, object],
    resolve_spec: Callable[[str], Path],
    spec_slug: Callable[[Path], str],
    plan_root: Path,
    workflow_report_root: Path,
    plan_callable: Callable[[object], int],
    slice_start_callable: Callable[[object], int],
    root: Path,
    rel: Callable[[Path], str],
    utc_now: Callable[[], str],
    json_dumps: Callable[[object], str],
) -> int:
    require_dirs()
    workflow_report_root.mkdir(parents=True, exist_ok=True)
    orchestrator, orchestrator_source, orchestrator_forced = workflow_orchestrator_settings(
        args,
        workspace_config=workspace_config,
    )

    spec_path = resolve_spec(args.spec)
    slug = spec_slug(spec_path)
    assets = workflow_assets(root)
    plan_path = plan_root / f"{slug}.json"
    if bool(getattr(args, "refresh_plan", False)) or not plan_path.exists():
        plan_stdout = io.StringIO()
        with contextlib.redirect_stdout(plan_stdout):
            plan_rc = plan_callable(type("PlanArgs", (), {"spec": slug})())
        if plan_rc != 0:
            return plan_rc

    plan_payload = json.loads(plan_path.read_text(encoding="utf-8"))
    handoffs: list[dict[str, object]] = []
    if bool(getattr(args, "start_slices", False)):
        for slice_payload in plan_payload.get("slices", []):
            if not isinstance(slice_payload, dict):
                continue
            slice_name = str(slice_payload.get("name", "")).strip()
            if not slice_name:
                continue
            slice_stdout = io.StringIO()
            with contextlib.redirect_stdout(slice_stdout):
                start_rc = slice_start_callable(type("SliceStartArgs", (), {"spec": slug, "slice": slice_name})())
            if start_rc != 0:
                return start_rc
            handoff_path = workflow_report_root.parent / f"{slug}-{slice_name}-handoff.md"
            handoffs.append(
                {
                    "slice": slice_name,
                    "repo": str(slice_payload.get("repo", "")),
                    "branch": str(slice_payload.get("branch", "")),
                    "worktree": str(slice_payload.get("worktree", "")),
                    "handoff": rel(handoff_path) if handoff_path.exists() else None,
                    "slice_start_output": [line for line in slice_stdout.getvalue().splitlines() if line.strip()],
                    "recommended_workflow": "quick-dev",
                    "workflow_path": rel(assets["bmad_quick_dev"]),
                }
            )

    payload = {
        "feature": slug,
        "generated_at": utc_now(),
        "stage": "execution-ready",
        "spec": rel(spec_path),
        "plan_path": rel(plan_path),
        "started_slices": bool(getattr(args, "start_slices", False)),
        "handoffs": handoffs,
        "default_orchestrator": orchestrator,
        "orchestrator_source": orchestrator_source,
        "orchestrator_forced": orchestrator_forced,
        "default_spec_engine": "tessl",
        "quick_dev_workflow": rel(assets["bmad_quick_dev"]),
        "story_cycle": {
            "create_story": rel(assets["bmad_create_story"]),
            "dev_story": rel(assets["bmad_dev_story"]),
            "sprint_status": rel(assets["bmad_sprint_status"]),
        },
        "next_commands": [
            flow_shell_command(["slice", "verify", slug, str(item["slice"]), "--json"]) for item in handoffs
        ]
        if handoffs
        else [
            flow_shell_command(["workflow", "next-step", slug, "--json"]),
        ],
    }

    json_path = workflow_report_root / f"{slug}-execute-feature.json"
    md_path = workflow_report_root / f"{slug}-execute-feature.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    lines = [
        f"# Workflow Execute Feature: {slug}",
        "",
        f"- Spec: `{rel(spec_path)}`",
        f"- Plan: `{rel(plan_path)}`",
        f"- Started slices: `{'yes' if payload['started_slices'] else 'no'}`",
        "",
        "## Default executor workflow",
        "",
        f"- `quick-dev`: `{rel(assets['bmad_quick_dev'])}`",
    ]
    if handoffs:
        lines.extend(["", "## Slice handoffs", ""])
        for item in handoffs:
            lines.append(
                f"- `{item['slice']}` -> repo=`{item['repo']}`, branch=`{item['branch']}`, "
                f"worktree=`{item['worktree']}`, handoff=`{item['handoff']}`"
            )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    payload["json_report"] = rel(json_path)
    payload["markdown_report"] = rel(md_path)
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
        return 0
    print(rel(json_path))
    print(rel(md_path))
    return 0


WORKFLOW_ENGINE_STAGES = [
    "plan",
    "slice_start",
    "ci_spec",
    "ci_repo",
    "ci_integration",
    "release_promote",
    "release_verify",
    "infra_apply",
]


def _workflow_callback(stage_event: str, payload: dict[str, object]) -> None:
    callback_url = str(os.environ.get("SOFTOS_GATEWAY_WORKFLOW_CALLBACK_URL", "")).strip()
    if not callback_url:
        return
    body = json.dumps({"event": stage_event, **payload}, ensure_ascii=True).encode("utf-8")
    request = urllib.request.Request(
        callback_url,
        data=body,
        method="POST",
        headers={"content-type": "application/json"},
    )
    try:
        urllib.request.urlopen(request, timeout=3).read()
    except (urllib.error.URLError, TimeoutError):
        return


def _ensure_engine_state(state: dict[str, object], *, utc_now: Callable[[], str]) -> dict[str, object]:
    engine = state.get("workflow_engine")
    if not isinstance(engine, dict):
        engine = {
            "status": "idle",
            "updated_at": utc_now(),
            "paused_at_stage": None,
            "stages": {},
        }
        state["workflow_engine"] = engine
    if not isinstance(engine.get("stages"), dict):
        engine["stages"] = {}
    return engine


def _stage_record(engine: dict[str, object], stage_name: str) -> dict[str, object]:
    stages = engine["stages"]
    assert isinstance(stages, dict)
    record = stages.get(stage_name)
    if not isinstance(record, dict):
        record = {
            "stage_name": stage_name,
            "started_at": None,
            "finished_at": None,
            "status": "skipped",
            "input_ref": None,
            "output_ref": None,
            "attempt": 0,
            "failure_reason": None,
        }
        stages[stage_name] = record
    return record


def _run_stage_callable(stage_name: str, slug: str, callables: dict[str, Callable[[object], int]]) -> tuple[int, str]:
    def _extract_output_ref(stdout_text: str, fallback_ref: str) -> str:
        text = stdout_text.strip()
        if not text:
            return fallback_ref
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                for key in ("json_report", "markdown_report", "report"):
                    value = str(parsed.get(key, "")).strip()
                    if value:
                        return value
        except json.JSONDecodeError:
            pass
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for candidate in reversed(lines):
            if candidate.endswith(".json") or candidate.endswith(".md"):
                return candidate
        return fallback_ref

    def _capture(callable_fn: Callable[[object], int], args_obj: object, fallback_ref: str) -> tuple[int, str]:
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            rc = callable_fn(args_obj)
        return rc, _extract_output_ref(captured.getvalue(), fallback_ref)

    if stage_name == "plan":
        rc, out = _capture(callables["plan"], type("PlanArgs", (), {"spec": slug})(), f"plan:{slug}")
        return rc, out
    if stage_name == "slice_start":
        plan_rc, _ = _capture(callables["plan"], type("PlanArgs", (), {"spec": slug})(), f"plan:{slug}")
        if plan_rc != 0:
            return plan_rc, "slice-start:plan-failed"
        exec_rc, exec_out = _capture(
            callables["execute_feature"],
            type("WorkflowExecuteArgs", (), {"spec": slug, "refresh_plan": False, "start_slices": True, "json": True})(),
            "execute-feature:start-slices",
        )
        return exec_rc, exec_out
    if stage_name == "ci_spec":
        rc, out = _capture(
            callables["ci_spec"],
            type("CiSpecArgs", (), {"spec": slug, "all": False, "changed": False, "base": None, "head": None, "json": True})(),
            "ci-spec",
        )
        return rc, out
    if stage_name == "ci_repo":
        rc, out = _capture(
            callables["ci_repo"],
            type(
                "CiRepoArgs",
                (),
                {"repo": None, "all": True, "spec": slug, "base": None, "head": None, "skip_install": False, "json": True},
            )(),
            "ci-repo",
        )
        return rc, out
    if stage_name == "ci_integration":
        rc, out = _capture(
            callables["ci_integration"],
            type("CiIntegrationArgs", (), {"profile": "smoke", "auto_up": False, "build": False, "json": True})(),
            "ci-integration",
        )
        return rc, out
    if stage_name == "release_promote":
        return 0, "release-promote:skipped-by-default"
    if stage_name == "release_verify":
        return 0, "release-verify:skipped-by-default"
    if stage_name == "infra_apply":
        return 0, "infra-apply:skipped-by-default"
    return 1, f"unknown-stage:{stage_name}"


def command_workflow_pause(
    args,
    *,
    resolve_spec: Callable[[str], Path],
    spec_slug: Callable[[Path], str],
    read_state: Callable[[str], dict[str, object]],
    write_state: Callable[[str, dict[str, object]], None],
    utc_now: Callable[[], str],
    json_dumps: Callable[[object], str],
) -> int:
    slug = spec_slug(resolve_spec(args.spec))
    state = read_state(slug)
    engine = _ensure_engine_state(state, utc_now=utc_now)
    engine["status"] = "paused"
    engine["paused_at_stage"] = str(args.stage).strip()
    engine["updated_at"] = utc_now()
    write_state(slug, state)
    payload = {"feature": slug, "status": "paused", "paused_at_stage": engine["paused_at_stage"], "updated_at": engine["updated_at"]}
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
    else:
        print(json.dumps(payload, ensure_ascii=True))
    return 0


def command_workflow_run(
    args,
    *,
    require_dirs: Callable[[], None],
    workspace_config: dict[str, object],
    resolve_spec: Callable[[str], Path],
    spec_slug: Callable[[Path], str],
    read_state: Callable[[str], dict[str, object]],
    write_state: Callable[[str, dict[str, object]], None],
    command_plan: Callable[[object], int],
    command_slice_start: Callable[[object], int],
    command_ci_spec: Callable[[object], int],
    command_ci_repo: Callable[[object], int],
    command_ci_integration: Callable[[object], int],
    command_release_promote: Callable[[object], int],
    command_release_verify: Callable[[object], int],
    command_infra_apply: Callable[[object], int],
    command_workflow_execute_feature: Callable[[object], int],
    workflow_report_root: Path,
    rel: Callable[[Path], str],
    utc_now: Callable[[], str],
    json_dumps: Callable[[object], str],
) -> int:
    require_dirs()
    workflow_report_root.mkdir(parents=True, exist_ok=True)
    _ = workflow_orchestrator_settings(args, workspace_config=workspace_config)
    slug = spec_slug(resolve_spec(args.spec))
    state = read_state(slug)
    engine = _ensure_engine_state(state, utc_now=utc_now)
    stage_reports: list[dict[str, object]] = []
    resume_from = str(getattr(args, "resume_from_stage", "") or "").strip()
    retry_stage = str(getattr(args, "retry_stage", "") or "").strip()
    explicit_pause = str(getattr(args, "pause_at_stage", "") or "").strip()
    inherited_pause = str(engine.get("paused_at_stage") or "").strip()
    pause_at = explicit_pause or inherited_pause
    if resume_from or retry_stage:
        # Resume/retry must not inherit an old pause marker.
        pause_at = explicit_pause
    if pause_at and pause_at not in WORKFLOW_ENGINE_STAGES:
        raise SystemExit(f"Etapa invalida para pause: `{pause_at}`.")
    if resume_from and resume_from not in WORKFLOW_ENGINE_STAGES:
        raise SystemExit(f"Etapa invalida para resume: `{resume_from}`.")
    if retry_stage and retry_stage not in WORKFLOW_ENGINE_STAGES:
        raise SystemExit(f"Etapa invalida para retry: `{retry_stage}`.")

    callables = {
        "plan": command_plan,
        "slice_start": command_slice_start,
        "ci_spec": command_ci_spec,
        "ci_repo": command_ci_repo,
        "ci_integration": command_ci_integration,
        "release_promote": command_release_promote,
        "release_verify": command_release_verify,
        "infra_apply": command_infra_apply,
        "execute_feature": command_workflow_execute_feature,
    }

    engine["status"] = "running"
    engine["paused_at_stage"] = pause_at or None
    engine["updated_at"] = utc_now()
    write_state(slug, state)

    start_from_stage = resume_from or retry_stage
    started_execution = False if start_from_stage else True
    finalized_status = "completed"
    for stage_name in WORKFLOW_ENGINE_STAGES:
        if start_from_stage and not started_execution:
            if stage_name != start_from_stage:
                continue
            started_execution = True
        record = _stage_record(engine, stage_name)
        if pause_at and stage_name == pause_at and not retry_stage:
            record["status"] = "skipped"
            record["failure_reason"] = "paused-before-stage"
            engine["status"] = "paused"
            engine["updated_at"] = utc_now()
            write_state(slug, state)
            finalized_status = "paused"
            break
        if record.get("status") == "passed" and retry_stage != stage_name:
            stage_reports.append({"stage_name": stage_name, "status": "skipped", "reason": "idempotent-already-passed"})
            continue

        record["attempt"] = int(record.get("attempt", 0) or 0) + 1
        record["stage_name"] = stage_name
        record["started_at"] = utc_now()
        record["finished_at"] = None
        record["status"] = "started"
        record["failure_reason"] = None
        record["input_ref"] = f"state:{slug}"
        _workflow_callback("stage_started", {"feature": slug, "stage_name": stage_name, "attempt": record["attempt"]})
        write_state(slug, state)

        rc, output_ref = _run_stage_callable(stage_name, slug, callables)
        record["output_ref"] = output_ref
        record["finished_at"] = utc_now()
        if rc == 0:
            if output_ref.endswith("skipped-by-default"):
                record["status"] = "skipped"
            else:
                record["status"] = "passed"
                _workflow_callback(
                    "stage_passed",
                    {"feature": slug, "stage_name": stage_name, "attempt": record["attempt"], "output_ref": output_ref},
                )
        else:
            record["status"] = "failed"
            record["failure_reason"] = f"stage `{stage_name}` failed with exit code {rc}."
            engine["status"] = "failed"
            _workflow_callback(
                "stage_failed",
                {
                    "feature": slug,
                    "stage_name": stage_name,
                    "attempt": record["attempt"],
                    "failure_reason": record["failure_reason"],
                },
            )
            write_state(slug, state)
            stage_reports.append(dict(record))
            finalized_status = "failed"
            break
        write_state(slug, state)
        stage_reports.append(dict(record))

    if finalized_status == "completed":
        engine["status"] = "completed"
    engine["updated_at"] = utc_now()
    write_state(slug, state)
    _workflow_callback("finalized", {"feature": slug, "status": finalized_status, "stages": stage_reports})

    payload = {
        "feature": slug,
        "status": finalized_status,
        "engine_status": engine["status"],
        "stages": stage_reports,
        "updated_at": engine["updated_at"],
    }
    json_path = workflow_report_root / f"{slug}-workflow-run.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    payload["json_report"] = rel(json_path)
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
    else:
        print(rel(json_path))
    return 1 if finalized_status == "failed" else 0
