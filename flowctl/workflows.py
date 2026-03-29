from __future__ import annotations

import contextlib
import io
import json
import os
import shlex
import textwrap
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from .multiagent import SchedulerConfig, run_slice_scheduler
from .quality_gates import (
    build_traceability_matrix,
    detect_api_dto_change,
    max_risk_level,
    required_checkpoints,
    risk_thresholds_by_level,
    slice_confidence_score,
)
from .specs import slice_governance_findings


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

    if str(frontmatter.get("status", "draft")).strip() == "approved":
        governance_findings = slice_governance_findings(
            analysis,
            planned_slices=plan_payload.get("slices", []) if isinstance(plan_payload, dict) else None,
        )
        if governance_findings:
            raise SystemExit(
                "La spec aprobada no cumple la gobernanza de slices:\n"
                + "\n".join(f"- {item}" for item in governance_findings)
            )

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
    analyze_spec: Callable[[Path], dict[str, object]],
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
    analysis = analyze_spec(spec_path)
    assets = workflow_assets(root)
    plan_path = plan_root / f"{slug}.json"
    if bool(getattr(args, "refresh_plan", False)) or not plan_path.exists():
        plan_stdout = io.StringIO()
        with contextlib.redirect_stdout(plan_stdout):
            plan_rc = plan_callable(type("PlanArgs", (), {"spec": slug})())
        if plan_rc != 0:
            return plan_rc

    plan_payload = json.loads(plan_path.read_text(encoding="utf-8"))
    governance_findings = slice_governance_findings(analysis, planned_slices=plan_payload.get("slices", []))
    if governance_findings:
        raise SystemExit(
            "No puedo ejecutar la feature porque el plan no cumple la gobernanza de slices:\n"
            + "\n".join(f"- {item}" for item in governance_findings)
        )
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


ERROR_CLASSES = ("infra", "dependencia", "validacion", "logica")


def _ensure_engine_state(state: dict[str, object], *, utc_now: Callable[[], str]) -> dict[str, object]:
    engine = state.get("workflow_engine")
    if not isinstance(engine, dict):
        engine = {
            "status": "idle",
            "updated_at": utc_now(),
            "paused_at_stage": None,
            "stages": {},
            "rollback": {
                "status": "idle",
                "updated_at": utc_now(),
                "stages": {},
            },
        }
        state["workflow_engine"] = engine
    if not isinstance(engine.get("stages"), dict):
        engine["stages"] = {}
    if not isinstance(engine.get("rollback"), dict):
        engine["rollback"] = {
            "status": "idle",
            "updated_at": utc_now(),
            "stages": {},
        }
    rollback = engine["rollback"]
    if not isinstance(rollback.get("stages"), dict):
        rollback["stages"] = {}
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
            "error_class": None,
        }
        stages[stage_name] = record
    if "error_class" not in record:
        record["error_class"] = record.get("error_class")
    return record


def _rollback_stage_record(engine: dict[str, object], stage_name: str, *, utc_now: Callable[[], str]) -> dict[str, object]:
    rollback = engine.get("rollback") or {}
    assert isinstance(rollback, dict)
    stages = rollback.get("stages")
    if not isinstance(stages, dict):
        stages = {}
        rollback["stages"] = stages
    record = stages.get(stage_name)
    if not isinstance(record, dict):
        record = {
            "stage_name": stage_name,
            "status": "pending",
            "compensated_at": None,
            "failure_reason": None,
        }
        stages[stage_name] = record
        rollback["updated_at"] = utc_now()
    return record


def _default_retry_policy() -> dict[str, dict[str, int]]:
    return {
        "infra": {"max_attempts": 3, "backoff_seconds": 0, "jitter_seconds": 0},
        "dependencia": {"max_attempts": 2, "backoff_seconds": 0, "jitter_seconds": 0},
        "validacion": {"max_attempts": 0, "backoff_seconds": 0, "jitter_seconds": 0},
        "logica": {"max_attempts": 0, "backoff_seconds": 0, "jitter_seconds": 0},
    }


def _retry_policy_for_error_class(
    *,
    error_class: str,
    workspace_config: dict[str, object],
) -> dict[str, int]:
    project = workspace_config.get("project", {}) if isinstance(workspace_config, dict) else {}
    workflow_cfg = project.get("workflow", {}) if isinstance(project, dict) else {}
    policy_cfg = workflow_cfg.get("retry_policy", {}) if isinstance(workflow_cfg, dict) else {}
    defaults = _default_retry_policy()
    if not isinstance(policy_cfg, dict):
        return defaults.get(error_class, {"max_attempts": 0, "backoff_seconds": 0, "jitter_seconds": 0})
    class_cfg = policy_cfg.get(error_class, {})
    if not isinstance(class_cfg, dict):
        return defaults.get(error_class, {"max_attempts": 0, "backoff_seconds": 0, "jitter_seconds": 0})
    result = dict(defaults.get(error_class, {}))
    for key in ("max_attempts", "backoff_seconds", "jitter_seconds"):
        if key in class_cfg:
            try:
                result[key] = int(class_cfg[key])
            except (TypeError, ValueError):
                continue
    return result


def _classify_failure(stage_name: str, failure_reason: str) -> str:
    text = (failure_reason or "").strip().lower()
    if text.startswith("checkpoint-failed:"):
        if "drift-check" in text or "contract-verify" in text or "generate-contracts" in text:
            return "validacion"
        if "confidence-threshold" in text or "additional-reviewer" in text:
            return "validacion"
    if "dependency-failed:" in text:
        return "dependencia"
    if stage_name in {"infra_apply"}:
        return "infra"
    if stage_name in {"ci_integration"}:
        return "infra"
    if stage_name in {"ci_repo", "ci_spec"}:
        return "dependencia"
    return "logica"


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


def _compute_reassignment_state(
    *,
    engine: dict[str, object],
    workflow_dlq: list[dict[str, object]],
    scheduler_report: dict[str, object] | None,
) -> tuple[bool, str]:
    status = str(engine.get("status", "")).strip()
    rollback = engine.get("rollback") or {}
    rollback_status = str(rollback.get("status", "")).strip()
    pending_items = rollback.get("pending_items") or []
    if status != "failed":
        return False, "engine-not-failed"
    if rollback_status not in {"idle", "completed"}:
        return False, f"rollback-status:{rollback_status or 'unknown'}"
    if pending_items:
        return False, "rollback-has-pending-items"
    if workflow_dlq:
        return False, "workflow-dlq-has-items"
    if scheduler_report is not None:
        jobs = [item for item in scheduler_report.get("jobs", []) if isinstance(item, dict)]
        running = [item for item in jobs if str(item.get("status")) in {"pending", "running"}]
        if running:
            return False, "scheduler-has-active-jobs"
    return True, ""


def _run_rollback_for_failed_stages(
    *,
    feature_slug: str,
    engine: dict[str, object],
    utc_now: Callable[[], str],
    workflow_report_root: Path,
    rel: Callable[[Path], str],
) -> dict[str, object]:
    rollback = engine.get("rollback") or {}
    if not isinstance(rollback, dict):
        rollback = {}
        engine["rollback"] = rollback

    stages = rollback.get("stages")
    if not isinstance(stages, dict):
        stages = {}
        rollback["stages"] = stages

    reverted_items: list[dict[str, object]] = []
    pending_items: list[dict[str, object]] = []
    manual_actions_required = False

    # Cargar ultimo scheduler report si existe (para slice_start).
    scheduler_json_path = workflow_report_root / f"{feature_slug}-scheduler.json"
    scheduler_report: dict[str, object] | None = None
    if scheduler_json_path.exists():
        try:
            scheduler_report = json.loads(scheduler_json_path.read_text(encoding="utf-8"))
        except Exception:
            scheduler_report = None

    engine_stages = engine.get("stages") or {}
    if not isinstance(engine_stages, dict):
        engine_stages = {}

    for stage_name in WORKFLOW_ENGINE_STAGES:
        stage_record = engine_stages.get(stage_name)
        if not isinstance(stage_record, dict):
            continue
        if str(stage_record.get("status")) != "passed":
            continue
        rb = stages.get(stage_name)
        if isinstance(rb, dict) and str(rb.get("status")) in {"completed", "partial", "failed", "skipped"}:
            # Idempotente: no repetir compensaciones ya registradas.
            continue

        rb = _rollback_stage_record(engine, stage_name, utc_now=utc_now)
        rb_items: list[dict[str, object]] = []
        rb_pending: list[dict[str, object]] = []
        rb_status = "completed"
        rb_failure_reason = ""

        if stage_name == "slice_start":
            # No tocamos repos/producto: compensacion es marcar pendientes manuales segun DLQ.
            dlq = []
            if isinstance(scheduler_report, dict):
                dlq = [item for item in scheduler_report.get("dlq", []) if isinstance(item, dict)]
            if dlq:
                rb_status = "partial"
                rb_pending.extend(
                    {
                        "kind": "slice",
                        "slice": str(item.get("slice", "")),
                        "reason": str(item.get("reason", "")),
                        "attempt": int(item.get("attempt", 0) or 0),
                    }
                    for item in dlq
                )
                manual_actions_required = True
            rb_items.append(
                {
                    "stage": stage_name,
                    "action": "mark-slices-for-manual-recovery",
                    "report": rel(scheduler_json_path) if scheduler_json_path.exists() else None,
                }
            )
        elif stage_name in {"release_promote", "infra_apply"}:
            # No-op compensable hoy: documentamos que no hay side-effects que revertir en este scope.
            rb_status = "skipped"
            rb_items.append(
                {
                    "stage": stage_name,
                    "action": "no-op",
                    "reason": "no-compensation-implemented-in-this-scope",
                }
            )
        else:
            rb_status = "skipped"
            rb_items.append(
                {
                    "stage": stage_name,
                    "action": "no-op",
                    "reason": "stage-has-no-registered-compensation",
                }
            )

        rb["status"] = rb_status
        rb["compensated_at"] = utc_now()
        rb["failure_reason"] = rb_failure_reason or None
        rb["pending_actions"] = rb_pending
        stages[stage_name] = rb
        reverted_items.extend(rb_items)
        pending_items.extend(rb_pending)

    # Agregar resumen en rollback.
    completed_stages = [name for name, rb in stages.items() if isinstance(rb, dict) and str(rb.get("status")) in {"completed", "skipped"}]
    partial_stages = [name for name, rb in stages.items() if isinstance(rb, dict) and str(rb.get("status")) == "partial"]
    failed_stages = [name for name, rb in stages.items() if isinstance(rb, dict) and str(rb.get("status")) == "failed"]
    if failed_stages or partial_stages:
        rollback_status = "partial"
    else:
        rollback_status = "completed" if completed_stages else "idle"

    rollback["status"] = rollback_status
    rollback["updated_at"] = utc_now()
    rollback["reverted_items"] = reverted_items
    rollback["pending_items"] = pending_items
    rollback["manual_actions_required"] = manual_actions_required
    summary_parts = []
    if completed_stages:
        summary_parts.append(f"completed_or_skipped:{','.join(completed_stages)}")
    if partial_stages:
        summary_parts.append(f"partial:{','.join(partial_stages)}")
    if failed_stages:
        summary_parts.append(f"failed:{','.join(failed_stages)}")
    rollback["summary"] = "; ".join(summary_parts) if summary_parts else "no-rollback-actions"
    return rollback


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
    command_drift_check: Callable[[object], int],
    command_contract_verify: Callable[[object], int],
    command_spec_generate_contracts: Callable[[object], int],
    plan_root: Path,
    workflow_report_root: Path,
    rel: Callable[[Path], str],
    utc_now: Callable[[], str],
    json_dumps: Callable[[object], str],
    sleep_fn: Callable[[float], None] = time.sleep,
) -> int:
    require_dirs()
    workflow_report_root.mkdir(parents=True, exist_ok=True)
    _ = workflow_orchestrator_settings(args, workspace_config=workspace_config)
    slug = spec_slug(resolve_spec(args.spec))
    state = read_state(slug)
    engine = _ensure_engine_state(state, utc_now=utc_now)
    stage_reports: list[dict[str, object]] = []
    checkpoint_reports: list[dict[str, object]] = []
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
    plan_path = plan_root / f"{slug}.json"
    plan_payload = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.exists() else None
    api_dto_change = detect_api_dto_change(plan_payload)
    risk_level = max_risk_level(plan_payload)
    thresholds = risk_thresholds_by_level()

    def _capture_json_callable(callable_fn: Callable[[object], int], args_obj: object) -> tuple[int, dict[str, object]]:
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            rc = callable_fn(args_obj)
        text = captured.getvalue().strip()
        if not text:
            return rc, {}
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return rc, parsed
        except json.JSONDecodeError:
            pass
        return rc, {}

    engine["status"] = "running"
    engine["paused_at_stage"] = pause_at or None
    engine["updated_at"] = utc_now()
    write_state(slug, state)

    start_from_stage = resume_from or retry_stage
    started_execution = False if start_from_stage else True
    finalized_status = "completed"
    workflow_dlq: list[dict[str, object]] = []
    scheduler_report_cache: dict[str, object] | None = None
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

        if stage_name == "slice_start":
            plan_stdout = io.StringIO()
            with contextlib.redirect_stdout(plan_stdout):
                plan_rc = command_plan(type("PlanArgs", (), {"spec": slug})())
            if plan_rc != 0:
                rc, output_ref = plan_rc, "slice-start:plan-failed"
            else:
                plan_path = plan_root / f"{slug}.json"
                if not plan_path.exists():
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
                    continue
                plan_payload = json.loads(plan_path.read_text(encoding="utf-8"))

                def _start_slice(slice_name: str) -> int:
                    args_obj = type("SliceStartArgs", (), {"spec": slug, "slice": slice_name})()
                    return command_slice_start(args_obj)

                scheduler_report = run_slice_scheduler(
                    feature_slug=slug,
                    plan_payload=plan_payload,
                    start_slice_callable=_start_slice,
                    utc_now=utc_now,
                    config=SchedulerConfig(
                        max_workers=max(1, int(os.environ.get("FLOW_SCHEDULER_MAX_WORKERS", "4"))),
                        per_repo_capacity=max(1, int(os.environ.get("FLOW_SCHEDULER_PER_REPO_CAPACITY", "1"))),
                        per_hot_area_capacity=max(1, int(os.environ.get("FLOW_SCHEDULER_PER_HOT_AREA_CAPACITY", "1"))),
                        lock_ttl_seconds=max(5, int(os.environ.get("FLOW_SCHEDULER_LOCK_TTL_SECONDS", "120"))),
                        max_retries_execution=max(0, int(os.environ.get("FLOW_SCHEDULER_MAX_RETRIES_EXECUTION", "1"))),
                    ),
                )
                scheduler_json = workflow_report_root / f"{slug}-scheduler.json"
                scheduler_md = workflow_report_root / f"{slug}-scheduler.md"
                scheduler_json.write_text(json.dumps(scheduler_report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
                scheduler_md.write_text(
                    textwrap.dedent(
                        f"""\
                        # Scheduler Report: {slug}

                        - Status: `{scheduler_report['status']}`
                        - Queue size: `{scheduler_report['queue_size']}`
                        - Max workers: `{scheduler_report['capacity']['max_workers']}`

                        ## Waits

                        {chr(10).join(f"- {item['slice']}: {item['reason']}" for item in scheduler_report['waits']) or '- none'}

                        ## Locks

                        {chr(10).join(f"- {item['lock']} owner={item['owner']}" for item in scheduler_report['locks']) or '- none'}

                        ## DLQ

                        {chr(10).join(f"- {item['slice']} reason={item['reason']} attempt={item['attempt']}" for item in scheduler_report['dlq']) or '- none'}
                        """
                    ),
                    encoding="utf-8",
                )
                rc = 0 if str(scheduler_report.get("status")) == "passed" else 1
                output_ref = rel(scheduler_json)
        else:
            rc, output_ref = _run_stage_callable(stage_name, slug, callables)

        # Retry loop by clase de error (infra, dependencia, validacion, logica)
        failure_reason = ""
        error_class = None
        while True:
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
                break

            failure_reason = f"stage `{stage_name}` failed with exit code {rc}."
            record["status"] = "failed"
            record["failure_reason"] = failure_reason
            error_class = _classify_failure(stage_name, failure_reason)
            record["error_class"] = error_class
            policy = _retry_policy_for_error_class(error_class=error_class, workspace_config=workspace_config)
            configured = int(policy.get("max_attempts", 0) or 0)
            max_attempts = configured if configured > 0 else 1
            if record["attempt"] >= max_attempts:
                engine["status"] = "failed"
                workflow_dlq.append(
                    {
                        "feature": slug,
                        "stage": stage_name,
                        "error_class": error_class,
                        "attempts": record["attempt"],
                        "failure_reason": record["failure_reason"],
                        "timestamp": utc_now(),
                    }
                )
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

            # Programar reintento sin corromper estado previo: marcar intento y re-ejecutar callable.
            stage_reports.append(
                {
                    "stage_name": stage_name,
                    "status": "retrying",
                    "attempt": record["attempt"],
                    "failure_reason": record["failure_reason"],
                    "error_class": error_class,
                }
            )
            write_state(slug, state)
            record["attempt"] = int(record.get("attempt", 0) or 0) + 1
            backoff = max(0, int(policy.get("backoff_seconds", 0) or 0))
            jitter = max(0, int(policy.get("jitter_seconds", 0) or 0))
            # Jitter deterministico simple basado en intento (estable y testeable).
            effective_jitter = min(jitter, max(0, record["attempt"] - 1))
            sleep_seconds = float(backoff + effective_jitter)
            if sleep_seconds > 0:
                sleep_fn(sleep_seconds)
            if stage_name == "slice_start":
                # slice_start ya recalcula scheduler en cada iteracion via plan + run_slice_scheduler
                plan_path = plan_root / f"{slug}.json"
                if not plan_path.exists():
                    rc, output_ref = _run_stage_callable(stage_name, slug, callables)
                else:
                    plan_payload = json.loads(plan_path.read_text(encoding="utf-8"))

                    def _start_slice(slice_name: str) -> int:
                        args_obj = type("SliceStartArgs", (), {"spec": slug, "slice": slice_name})()
                        return command_slice_start(args_obj)

                    scheduler_report = run_slice_scheduler(
                        feature_slug=slug,
                        plan_payload=plan_payload,
                        start_slice_callable=_start_slice,
                        utc_now=utc_now,
                        config=SchedulerConfig(
                            max_workers=max(1, int(os.environ.get("FLOW_SCHEDULER_MAX_WORKERS", "4"))),
                            per_repo_capacity=max(1, int(os.environ.get("FLOW_SCHEDULER_PER_REPO_CAPACITY", "1"))),
                            per_hot_area_capacity=max(1, int(os.environ.get("FLOW_SCHEDULER_PER_HOT_AREA_CAPACITY", "1"))),
                            lock_ttl_seconds=max(5, int(os.environ.get("FLOW_SCHEDULER_LOCK_TTL_SECONDS", "120"))),
                            max_retries_execution=max(0, int(os.environ.get("FLOW_SCHEDULER_MAX_RETRIES_EXECUTION", "1"))),
                        ),
                    )
                    scheduler_json = workflow_report_root / f"{slug}-scheduler.json"
                    scheduler_md = workflow_report_root / f"{slug}-scheduler.md"
                    scheduler_json.write_text(json.dumps(scheduler_report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
                    scheduler_md.write_text(
                        textwrap.dedent(
                            f"""\
                            # Scheduler Report: {slug}

                            - Status: `{scheduler_report['status']}`
                            - Queue size: `{scheduler_report['queue_size']}`
                            - Max workers: `{scheduler_report['capacity']['max_workers']}`

                            ## Waits

                            {chr(10).join(f"- {item['slice']}: {item['reason']}" for item in scheduler_report['waits']) or '- none'}

                            ## Locks

                            {chr(10).join(f"- {item['lock']} owner={item['owner']}" for item in scheduler_report['locks']) or '- none'}

                            ## DLQ

                            {chr(10).join(f"- {item['slice']} reason={item['reason']} attempt={item['attempt']}" for item in scheduler_report['dlq']) or '- none'}
                            """
                        ),
                        encoding="utf-8",
                    )
                    rc = 0 if str(scheduler_report.get("status")) == "passed" else 1
                    output_ref = rel(scheduler_json)
                    scheduler_report_cache = scheduler_report
            else:
                rc, output_ref = _run_stage_callable(stage_name, slug, callables)
        if finalized_status == "failed":
            break

        stage_checkpoint_results: list[dict[str, object]] = []
        required = required_checkpoints(stage_name, risk_level, api_dto_change)
        stage_checkpoint_results.append(
            {
                "checkpoint": f"{stage_name}-stage-pass",
                "required": f"{stage_name}-stage-pass" in required,
                "status": "passed" if record["status"] in {"passed", "skipped"} else "failed",
                "reason": f"stage-status:{record['status']}",
            }
        )
        if stage_name == "ci_spec":
            drift_rc, drift_payload = _capture_json_callable(
                command_drift_check,
                type("DriftArgs", (), {"spec": slug, "all": False, "changed": False, "base": None, "head": None, "json": True})(),
            )
            drift_ok = drift_rc == 0
            stage_checkpoint_results.append(
                {
                    "checkpoint": "drift-check-pass",
                    "required": "drift-check-pass" in required,
                    "status": "passed" if drift_ok else "failed",
                    "reason": "" if drift_ok else "drift-check-failed",
                    "report": drift_payload.get("json_report"),
                }
            )
            if api_dto_change:
                gen_rc, gen_payload = _capture_json_callable(
                    command_spec_generate_contracts,
                    type("GenerateContractsArgs", (), {"spec": slug, "json": True})(),
                )
                artifacts = gen_payload.get("artifacts", [])
                generate_ok = gen_rc == 0 and isinstance(artifacts, list) and bool(artifacts)
                stage_checkpoint_results.append(
                    {
                        "checkpoint": "generate-contracts-pass",
                        "required": True,
                        "status": "passed" if generate_ok else "failed",
                        "reason": "" if generate_ok else "missing-generated-contracts",
                    }
                )
                contract_rc, contract_payload = _capture_json_callable(
                    command_contract_verify,
                    type("ContractVerifyArgs", (), {"spec": slug, "all": False, "changed": False, "base": None, "head": None, "json": True})(),
                )
                contract_ok = contract_rc == 0
                stage_checkpoint_results.append(
                    {
                        "checkpoint": "contract-verify-pass",
                        "required": True,
                        "status": "passed" if contract_ok else "failed",
                        "reason": "" if contract_ok else "contract-verify-failed",
                        "report": contract_payload.get("json_report"),
                    }
                )
        if stage_name == "ci_integration" and risk_level in {"high", "critical"}:
            ext_rc, _ = _capture_json_callable(
                command_ci_integration,
                type("CiIntegrationExtendedArgs", (), {"profile": "smoke:ci-clean", "auto_up": True, "build": False, "json": True})(),
            )
            stage_checkpoint_results.append(
                {
                    "checkpoint": "ci-integration-extended-pass",
                    "required": True,
                    "status": "passed" if ext_rc == 0 else "failed",
                    "reason": "" if ext_rc == 0 else "integration-extended-failed",
                }
            )
        if stage_name == "release_promote":
            stage_records_map = {
                str(item.get("stage_name")): item for item in stage_reports if isinstance(item, dict) and item.get("stage_name")
            }
            stage_records_map[stage_name] = dict(record)
            drift_ok = any(
                item["checkpoint"] == "drift-check-pass" and item["status"] == "passed" for item in checkpoint_reports + stage_checkpoint_results
            )
            contract_ok = any(
                item["checkpoint"] == "contract-verify-pass" and item["status"] == "passed" for item in checkpoint_reports + stage_checkpoint_results
            ) or (not api_dto_change)
            slice_scores = []
            for slice_payload in (plan_payload or {}).get("slices", []) if isinstance(plan_payload, dict) else []:
                if not isinstance(slice_payload, dict):
                    continue
                slice_scores.append(
                    slice_confidence_score(
                        slice_payload=slice_payload,
                        stage_records=stage_records_map,
                        contract_ok=contract_ok,
                        drift_ok=drift_ok,
                    )
                )
            threshold = thresholds.get(risk_level, 50)
            confidence_ok = all(int(item["score"]) >= threshold for item in slice_scores) if slice_scores else True
            stage_checkpoint_results.append(
                {
                    "checkpoint": "confidence-threshold-pass",
                    "required": True,
                    "status": "passed" if confidence_ok else "failed",
                    "reason": "" if confidence_ok else f"confidence-below-threshold:{threshold}",
                    "threshold": threshold,
                }
            )
            if risk_level in {"high", "critical"}:
                reviewer_ok = bool(str(os.environ.get("FLOW_QUALITY_ADDITIONAL_REVIEWER", "")).strip())
                stage_checkpoint_results.append(
                    {
                        "checkpoint": "additional-reviewer-pass",
                        "required": True,
                        "status": "passed" if reviewer_ok else "failed",
                        "reason": "" if reviewer_ok else "missing-additional-reviewer",
                    }
                )

        checkpoint_reports.extend(stage_checkpoint_results)
        failed_required = [item for item in stage_checkpoint_results if item.get("required") and item.get("status") != "passed"]
        if failed_required:
            first = failed_required[0]
            record["status"] = "failed"
            record["failure_reason"] = f"checkpoint-failed:{first['checkpoint']}:{first.get('reason', '')}".rstrip(":")
            engine["status"] = "failed"
            write_state(slug, state)
            stage_reports.append(dict(record))
            finalized_status = "failed"
            break
        write_state(slug, state)
        stage_reports.append(dict(record))

    rollback_payload: dict[str, object]
    rollback_last_failure: dict[str, object] | None = None
    if finalized_status == "completed":
        engine["status"] = "completed"
        # En runs exitosos no ejecutamos rollback: reportamos rollback neutral
        # para esta corrida y, si existe, exponemos el historial previo de forma separada.
        existing_rb = engine.get("rollback")
        if isinstance(existing_rb, dict) and existing_rb:
            rollback_last_failure = dict(existing_rb)
        rollback_payload = {
            "status": "idle",
            "updated_at": utc_now(),
            "stages": {},
            "reverted_items": [],
            "pending_items": [],
            "manual_actions_required": False,
            "summary": "no-rollback-actions",
        }
    else:
        # Ejecutar rollback solo en fallos para dejar estado consistente y auditable.
        rollback_payload = _run_rollback_for_failed_stages(
            feature_slug=slug,
            engine=engine,
            utc_now=utc_now,
            workflow_report_root=workflow_report_root,
            rel=rel,
        )

    engine["updated_at"] = utc_now()
    write_state(slug, state)
    _workflow_callback("finalized", {"feature": slug, "status": finalized_status, "stages": stage_reports})

    payload = {
        "feature": slug,
        "status": finalized_status,
        "engine_status": engine["status"],
        "stages": stage_reports,
        "quality_checkpoints": checkpoint_reports,
        "updated_at": engine["updated_at"],
        "rollback": rollback_payload,
        "workflow_dlq": workflow_dlq,
    }
    if rollback_last_failure is not None:
        payload["rollback_last_failure"] = rollback_last_failure
    stage_records_map = {
        str(item.get("stage_name")): item for item in stage_reports if isinstance(item, dict) and item.get("stage_name")
    }
    drift_ok = any(item.get("checkpoint") == "drift-check-pass" and item.get("status") == "passed" for item in checkpoint_reports)
    contract_ok = any(item.get("checkpoint") == "contract-verify-pass" and item.get("status") == "passed" for item in checkpoint_reports) or (
        not api_dto_change
    )
    slice_scores: list[dict[str, object]] = []
    for slice_payload in (plan_payload or {}).get("slices", []) if isinstance(plan_payload, dict) else []:
        if not isinstance(slice_payload, dict):
            continue
        slice_scores.append(
            slice_confidence_score(
                slice_payload=slice_payload,
                stage_records=stage_records_map,
                contract_ok=contract_ok,
                drift_ok=drift_ok,
            )
        )
    payload["quality"] = {
        "risk_level": risk_level,
        "thresholds": thresholds,
        "api_dto_change": api_dto_change,
        "slice_scores": slice_scores,
        "traceability_matrix": build_traceability_matrix(
            feature_slug=slug,
            plan_payload=plan_payload,
            state=state,
            stage_records=stage_records_map,
        ),
    }
    json_path = workflow_report_root / f"{slug}-workflow-run.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    payload["json_report"] = rel(json_path)
    reassignment_ready, reassignment_reason = _compute_reassignment_state(
        engine=engine,
        workflow_dlq=workflow_dlq,
        scheduler_report=scheduler_report_cache,
    )
    payload["reassignment_ready"] = reassignment_ready
    if not reassignment_ready:
        payload["reassignment_reason"] = reassignment_reason
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
    else:
        print(rel(json_path))
    return 1 if finalized_status == "failed" else 0
