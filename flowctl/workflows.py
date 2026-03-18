from __future__ import annotations

import contextlib
import io
import json
import shlex
import textwrap
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


def _doctor_payload(
    *,
    root: Path,
    rel: Callable[[Path], str],
    capture_workspace_tool: Callable[[list[str]], dict[str, object]],
    bmad_command_prefix: Callable[[], list[str]],
    load_skills_config,
    skills_entries,
) -> dict[str, object]:
    assets = workflow_assets(root)
    findings: list[str] = []

    payload = {
        "default_orchestrator": "bmad",
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

    spec_stdout = io.StringIO()
    with contextlib.redirect_stdout(spec_stdout):
        spec_rc = spec_create_callable(spec_args)
    if spec_rc != 0:
        return spec_rc

    spec_path = feature_specs / f"{slug}.spec.md"
    assets = workflow_assets(root)
    doctor = _doctor_payload(
        root=root,
        rel=rel,
        capture_workspace_tool=capture_workspace_tool,
        bmad_command_prefix=bmad_command_prefix,
        load_skills_config=load_skills_config,
        skills_entries=skills_entries,
    )

    payload = {
        "feature": slug,
        "stage": "intake",
        "generated_at": utc_now(),
        "spec": rel(spec_path),
        "state": rel(state_path(slug)),
        "spec_create_output": [line for line in spec_stdout.getvalue().splitlines() if line.strip()],
        "default_orchestrator": "bmad",
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
            - Default orchestrator: `bmad`
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
        "default_orchestrator": "bmad",
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
        "default_orchestrator": "bmad",
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
