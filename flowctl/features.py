from __future__ import annotations

import fnmatch
import json
import os
import shlex
import sqlite3
import subprocess
import textwrap
from pathlib import Path
from typing import Callable, Optional

from .specs import (
    frontmatter_status_allows_execution,
    frontmatter_status_is_terminal,
    slice_execution_contract,
    slice_governance_findings,
)


def render_yaml_list(key: str, values: list[str]) -> list[str]:
    items = [str(value).strip() for value in values if str(value).strip()]
    if not items:
        return [f"{key}: []"]
    return [f"{key}:"] + [f"  - {item}" for item in items]


def normalize_description(value: object) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line).strip()


def normalize_acceptance_criteria(values: object) -> list[str]:
    if values is None:
        return []
    if isinstance(values, list):
        candidates = values
    else:
        candidates = [values]
    items: list[str] = []
    for candidate in candidates:
        if candidate is None:
            continue
        text = str(candidate).replace("\r\n", "\n").replace("\r", "\n")
        for line in text.split("\n"):
            normalized = line.strip().lstrip("-* ").strip()
            if normalized:
                items.append(normalized)
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def load_plan_and_slice(
    slug: str,
    slice_name: str,
    *,
    plan_root: Path,
    rel: Callable[[Path], str],
) -> tuple[dict[str, object], dict[str, object], Path]:
    plan_path = plan_root / f"{slug}.json"
    if not plan_path.exists():
        raise SystemExit(f"No existe plan para '{slug}'. Ejecuta `python3 ./flow plan {slug}` primero.")

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    slices = plan.get("slices", [])
    selected = next((item for item in slices if item["name"] == slice_name), None)
    if selected is None:
        raise SystemExit(f"No existe la slice '{slice_name}' en {rel(plan_path)}.")

    return plan, selected, plan_path


def matches_any_pattern(path: str, patterns: list[str]) -> bool:
    normalized = path.replace("\\", "/")
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in patterns)


def resolve_slice_inspection_path(*, repo_path: Path, planned_worktree: Path, root: Path) -> Path:
    if not planned_worktree.exists():
        return repo_path
    try:
        repo_relative_path = repo_path.resolve().relative_to(root.resolve())
    except ValueError:
        return planned_worktree

    candidate = planned_worktree / repo_relative_path
    if candidate.exists():
        return candidate
    return planned_worktree


def command_spec_create(
    args,
    *,
    require_dirs: Callable[[], None],
    slugify: Callable[[str], str],
    implementation_repos: Callable[[], list[str]],
    root_repo: str,
    feature_specs: Path,
    default_targets: dict[str, list[str]],
    render_targets: Callable[[list[str]], str],
    render_test_plan_hints: Callable[[list[str]], str],
    rel: Callable[[Path], str],
    state_path: Callable[[str], Path],
    utc_now: Callable[[], str],
    write_state: Callable[[str, dict[str, object]], None],
) -> int:
    require_dirs()

    slug = slugify(args.slug)
    title = args.title.strip()
    repos = args.repo or implementation_repos()[:1] or [root_repo]
    required_runtimes = [str(item).strip() for item in getattr(args, "runtime", []) or [] if str(item).strip()]
    required_services = [str(item).strip() for item in getattr(args, "service", []) or [] if str(item).strip()]
    required_capabilities = [
        str(item).strip() for item in getattr(args, "capability", []) or [] if str(item).strip()
    ]
    depends_on = [slugify(str(item)) for item in getattr(args, "depends_on", []) or [] if str(item).strip()]
    acceptance_criteria = normalize_acceptance_criteria(getattr(args, "acceptance_criteria", []))
    acceptance_lines = [f"- {item}" for item in acceptance_criteria] or ["- TODO", "- TODO"]
    intake_description = normalize_description(getattr(args, "description", ""))
    description_lines = [line for line in intake_description.split("\n") if line]
    summary_description = (
        description_lines[0]
        if description_lines
        else "TODO describir el resultado observable"
    )
    objective_text = (
        description_lines[0]
        if description_lines
        else "Describir el comportamiento observable que esta feature debe introducir."
    )
    context_section = (
        [
            "Contexto inicial capturado desde intake:",
            "",
            *[f"- {line}" for line in description_lines],
            "",
        ]
        if description_lines
        else [
            "- por que existe ahora",
            "- que foundations gobiernan esta feature",
            "- que repos estan afectados",
            "- que runtimes, servicios o capabilities deben existir para materializarla",
            "",
        ]
    )
    problem_section = (
        [
            "- derivado del requerimiento inbound descrito en Contexto",
            "- validar supuestos y riesgos durante refinement",
            "",
        ]
        if description_lines
        else [
            "- que duele hoy",
            "- que riesgo o ineficiencia se quiere eliminar",
            "",
        ]
    )
    inbound_description_block = (
        [
            "## Descripcion inbound",
            "",
            *[f"- {line}" for line in description_lines],
            "",
        ]
        if description_lines
        else []
    )
    spec_path = feature_specs / f"{slug}.spec.md"
    if spec_path.exists():
        raise SystemExit(f"La spec ya existe: {rel(spec_path)}")

    target_block = render_targets(repos)
    repo_rows = "\n".join(f"| `{repo}` | {', '.join(default_targets[repo])} |" for repo in repos)
    body = "\n".join(
        [
            "---",
            "schema_version: 3",
            f"name: {json.dumps(title, ensure_ascii=True)}",
            f"description: {json.dumps(summary_description, ensure_ascii=True)}",
            "status: draft",
            "owner: platform",
            "single_slice_reason: \"\"",
            "multi_domain: false",
            "phases: []",
            *render_yaml_list("depends_on", depends_on),
            *render_yaml_list("required_runtimes", required_runtimes),
            *render_yaml_list("required_services", required_services),
            *render_yaml_list("required_capabilities", required_capabilities),
            "stack_projects: []",
            "stack_services: []",
            "stack_capabilities: []",
            "targets:",
            target_block,
            "---",
            "",
            f"# {title}",
            "",
            "## Objetivo",
            "",
            objective_text,
            "",
            "## Contexto",
            "",
            *context_section,
            "",
            "## Foundations Aplicables",
            "",
            "- spec foundation requerida: `specs/000-foundation/...`",
            "- justificacion si no aplica alguna foundation relevante",
            "",
            "## Domains Aplicables",
            "",
            "- spec domain requerida: `specs/domains/...`",
            "- si no aplica domain, declarar explicitamente: `no aplica domain porque <razon>`",
            "",
            "## Problema a resolver",
            "",
            *problem_section,
            *inbound_description_block,
            "",
            "## Alcance",
            "",
            "### Incluye",
            "",
            "- TODO",
            "- TODO",
            "",
            "### No incluye",
            "",
            "- TODO",
            "- TODO",
            "",
            "## Repos afectados",
            "",
            "| Repo | Targets |",
            "| --- | --- |",
            repo_rows,
            "",
            "## Resultado esperado",
            "",
            "- TODO",
            "",
            "## Reglas de negocio",
            "",
            "- TODO",
            "",
            "## Flujo principal",
            "",
            "1. TODO",
            "2. TODO",
            "3. TODO",
            "",
            "## Contrato funcional",
            "",
            "- inputs clave",
            "- outputs clave",
            "- errores esperados",
            "- side effects relevantes",
            "",
            "## Routing de implementacion",
            "",
            "- El repo se deduce desde `targets`.",
            "- Cada slice debe pertenecer a un solo repo.",
            "- El plan operativo vive en `.flow/plans/**`.",
            "- Las dependencias estructurales viven en el frontmatter y deben resolverse antes de aprobar.",
            "",
            "## Slice Breakdown",
            "",
            "```yaml",
            "- name: <slice-name>",
            "  targets:",
            "    - <target-de-esta-slice>",
            "  hot_area: <repo/area-caliente>",
            "  depends_on: []",
            "```",
            "",
            "## Criterios de aceptacion",
            "",
            *acceptance_lines,
            "",
            "## Test plan",
            "",
            render_test_plan_hints(repos),
            "",
            "## Rollout",
            "",
            "- TODO",
            "",
            "## Rollback",
            "",
            "- TODO",
            "",
        ]
    )
    spec_path.write_text(body, encoding="utf-8")

    state = {
        "feature": slug,
        "title": title,
        "spec_path": rel(spec_path),
        "status": "draft-spec",
        "repos": repos,
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    write_state(slug, state)

    print(rel(spec_path))
    print(rel(state_path(slug)))
    return 0


def command_spec_review(
    args,
    *,
    require_dirs: Callable[[], None],
    resolve_spec: Callable[[str], Path],
    spec_slug: Callable[[Path], str],
    analyze_spec: Callable[[Path], dict[str, object]],
    repos_missing_test_refs: Callable[[dict[str, list[dict[str, str]]], dict[str, list[dict[str, str]]]], list[str]],
    spec_dependency_findings: Callable[[dict[str, object]], list[str]],
    format_findings: Callable[[list[str]], list[str]],
    report_root: Path,
    read_state: Callable[[str], dict[str, object]],
    write_state: Callable[[str, dict[str, object]], None],
    rel: Callable[[Path], str],
    utc_now: Callable[[], str],
    json_dumps: Callable[[object], str],
) -> int:
    require_dirs()
    spec_path = resolve_spec(args.spec)
    slug = spec_slug(spec_path)
    analysis = analyze_spec(spec_path)
    frontmatter = analysis["frontmatter"]

    high_priority: list[str] = []
    medium_priority: list[str] = []
    low_priority: list[str] = []

    high_priority.extend(str(error) for error in analysis["frontmatter_errors"])
    for field in analysis["missing_frontmatter"]:
        high_priority.append(f"Falta el campo de frontmatter `{field}`.")

    high_priority.extend(str(error) for error in analysis["target_errors"])
    high_priority.extend(str(error) for error in analysis["test_errors"])
    high_priority.extend(spec_dependency_findings(analysis))
    high_priority.extend(slice_governance_findings(analysis))

    description = str(frontmatter.get("description", "")).strip().lower()
    if not description or description.startswith("todo"):
        medium_priority.append("`description` sigue en placeholder y no describe el resultado observable.")

    missing_repo_tests = repos_missing_test_refs(analysis["target_index"], analysis["test_index"])
    if missing_repo_tests:
        medium_priority.append(
            "Faltan referencias `[@test]` para: " + ", ".join(sorted(missing_repo_tests)) + "."
        )

    todo_count = int(analysis["todo_count"])
    if todo_count:
        medium_priority.append(f"Quedan {todo_count} placeholders `TODO` en la spec.")

    status = str(frontmatter.get("status", "draft")).strip() or "draft"
    if status not in {"draft", "approved"}:
        low_priority.append(f"El estado `{status}` no forma parte del flujo principal esperado.")

    ready_to_approve = not high_priority and not medium_priority
    report_path = report_root / f"{slug}-spec-review.md"
    report = textwrap.dedent(
        f"""\
        # Spec Review

        ## Documento revisado

        - `{rel(spec_path)}`

        ## Findings

        ### Alta prioridad

        {chr(10).join(format_findings(high_priority))}

        ### Media prioridad

        {chr(10).join(format_findings(medium_priority))}

        ### Baja prioridad

        {chr(10).join(format_findings(low_priority))}

        ## Aprobacion

        - [{'x' if ready_to_approve else ' '}] lista para aprobar
        - [{' ' if ready_to_approve else 'x'}] requiere cambios

        ## Notas

        - Estado actual del frontmatter: `{status}`
        - Schema version: `{analysis['schema_version']}`
        - Targets declarados: `{len(analysis['targets'])}`
        - Referencias `[@test]`: `{len(analysis['test_refs'])}`
        - `depends_on`: `{len(analysis['depends_on'])}`
        - `required_runtimes`: `{len(analysis['required_runtimes'])}`
        - `required_services`: `{len(analysis['required_services'])}`
        - `required_capabilities`: `{len(analysis['required_capabilities'])}`
        - `stack_projects`: `{len(analysis['stack_projects'])}`
        - `stack_services`: `{len(analysis['stack_services'])}`
        - `stack_capabilities`: `{len(analysis['stack_capabilities'])}`
        """
    )
    report_path.write_text(report, encoding="utf-8")

    payload = {
        "spec": rel(spec_path),
        "report": rel(report_path),
        "ready_to_approve": ready_to_approve,
        "result": "ready_to_approve" if ready_to_approve else "changes_required",
        "reviewed_at": utc_now(),
        "frontmatter_status": status,
        "schema_version": analysis["schema_version"],
        "targets_declared": len(analysis["targets"]),
        "test_refs": len(analysis["test_refs"]),
        "depends_on": list(analysis["depends_on"]),
        "required_runtimes": list(analysis["required_runtimes"]),
        "required_services": list(analysis["required_services"]),
        "required_capabilities": list(analysis["required_capabilities"]),
        "stack_projects": list(analysis["stack_projects"]),
        "stack_services": list(analysis["stack_services"]),
        "stack_capabilities": list(analysis["stack_capabilities"]),
        "findings": {
            "high": high_priority,
            "medium": medium_priority,
            "low": low_priority,
        },
    }

    state = read_state(slug)
    state.update(
        {
            "feature": slug,
            "spec_path": rel(spec_path),
            "status": "reviewing-spec",
            "last_review": {
                "report": rel(report_path),
                "ready_to_approve": ready_to_approve,
                "reviewed_at": payload["reviewed_at"],
                "result": payload["result"],
                "spec_mtime_ns": spec_path.stat().st_mtime_ns,
            },
        }
    )
    write_state(slug, state)
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
        return 0
    print(rel(report_path))
    return 0


def command_spec_approve(
    args,
    *,
    resolve_spec: Callable[[str], Path],
    spec_slug: Callable[[Path], str],
    ensure_spec_ready_for_approval: Callable[[Path], dict[str, object]],
    replace_frontmatter_status: Callable[[Path, str], None],
    read_state: Callable[[str], dict[str, object]],
    write_state: Callable[[str, dict[str, object]], None],
    rel: Callable[[Path], str],
    utc_now: Callable[[], str],
) -> int:
    spec_path = resolve_spec(args.spec)
    slug = spec_slug(spec_path)
    state = read_state(slug)
    review = state.get("last_review", {})
    if not isinstance(review, dict):
        review = {}

    if not review:
        raise SystemExit(
            f"La spec `{rel(spec_path)}` requiere una review previa. Ejecuta `python3 ./flow spec review {slug}`."
        )
    if not bool(review.get("ready_to_approve")):
        raise SystemExit(
            f"La ultima review de `{rel(spec_path)}` no quedo lista para aprobar. Revisa `{review.get('report', 'sin reporte')}`."
        )
    reviewed_mtime = int(review.get("spec_mtime_ns", 0) or 0)
    current_mtime = spec_path.stat().st_mtime_ns
    if reviewed_mtime != current_mtime:
        raise SystemExit(
            f"La spec `{rel(spec_path)}` cambio despues de la ultima review. Ejecuta `python3 ./flow spec review {slug}` de nuevo."
        )

    approver = (
        str(getattr(args, "approver", "") or "").strip()
        or os.environ.get("FLOW_APPROVER", "").strip()
        or os.environ.get("USER", "").strip()
        or os.environ.get("USERNAME", "").strip()
    )
    if not approver:
        raise SystemExit("`spec approve` requiere `--approver` o una identidad en `FLOW_APPROVER/USER`.")

    analysis = ensure_spec_ready_for_approval(spec_path)
    replace_frontmatter_status(spec_path, "approved")
    state.update(
        {
            "feature": slug,
            "title": analysis["frontmatter"].get("name", slug),
            "spec_path": rel(spec_path),
            "status": "approved-spec",
            "repos": list(analysis["target_index"]),
            "last_approval": {
                "approver": approver,
                "approved_at": utc_now(),
                "review_report": review.get("report"),
            },
        }
    )
    write_state(slug, state)
    print(f"Spec aprobada por {approver}: {rel(spec_path)}")
    return 0


def command_plan(
    args,
    *,
    require_dirs: Callable[[], None],
    resolve_spec: Callable[[str], Path],
    spec_slug: Callable[[Path], str],
    analyze_spec: Callable[[Path], dict[str, object]],
    require_routed_paths: Callable[[list[str], str], dict[str, list[dict[str, str]]]],
    repo_slice_prefix: Callable[[str], str],
    repo_root: Callable[[str], Path],
    worktree_root: Path,
    plan_root: Path,
    read_state: Callable[[str], dict[str, object]],
    write_state: Callable[[str, dict[str, object]], None],
    rel: Callable[[Path], str],
    utc_now: Callable[[], str],
) -> int:
    require_dirs()
    spec_path = resolve_spec(args.spec)
    slug = spec_slug(spec_path)
    analysis = analyze_spec(spec_path)
    frontmatter = analysis["frontmatter"]
    if frontmatter_status_is_terminal(frontmatter.get("status")):
        raise SystemExit(f"La spec '{slug}' ya esta en estado `released`; no se debe planear de nuevo.")
    if not frontmatter_status_allows_execution(frontmatter.get("status")):
        raise SystemExit(f"La spec '{slug}' debe estar en estado `approved` antes de planearla.")

    if analysis["target_errors"]:
        joined = "\n".join(f"- {error}" for error in analysis["target_errors"])
        raise SystemExit(f"La spec tiene targets invalidos:\n{joined}")

    target_index = require_routed_paths(analysis["targets"], "targets")
    repos = list(target_index)
    plan_findings = slice_governance_findings(analysis)
    if plan_findings:
        joined = "\n".join(f"- {item}" for item in plan_findings)
        raise SystemExit(f"La spec no cumple la gobernanza de slices:\n{joined}")

    slices: list[dict[str, object]] = []
    slice_breakdown = [item for item in analysis.get("slice_breakdown", []) if isinstance(item, dict)]
    if slice_breakdown:
        for slice_spec in slice_breakdown:
            repo = str(slice_spec["repo"])
            raw_name = str(slice_spec.get("name", "")).strip()
            safe_name = "".join(ch.lower() if ch.isalnum() else "-" for ch in raw_name).strip("-") or "slice"
            owned_targets = [str(target) for target in slice_spec.get("targets", [])]
            owned_patterns = [
                str(entry["relative"])
                for entry in slice_spec.get("target_index", {}).get(repo, [])
                if isinstance(entry, dict) and str(entry.get("relative", "")).strip()
            ]
            linked_tests = [item["raw"] for item in analysis["test_index"].get(repo, [])]
            linked_test_patterns = [item["relative"] for item in analysis["test_index"].get(repo, [])]
            execution_contract = slice_execution_contract(slice_spec)
            slices.append(
                {
                    "name": raw_name,
                    "repo": repo,
                    "repo_path": str(repo_root(repo).resolve()),
                    "branch": f"feat/{slug}-{safe_name}",
                    "worktree": str((worktree_root / f"{repo}-{slug}-{safe_name}").resolve()),
                    "owned_targets": owned_targets,
                    "owned_patterns": owned_patterns,
                    "linked_tests": linked_tests,
                    "linked_test_patterns": linked_test_patterns,
                    "hot_area": str(slice_spec.get("hot_area", "")).strip(),
                    "depends_on": [str(item).strip() for item in slice_spec.get("depends_on", []) if str(item).strip()],
                    "semantic_locks": [
                        str(item).strip() for item in slice_spec.get("semantic_locks", []) if str(item).strip()
                    ],
                    **execution_contract,
                    "status": "slice-ready",
                }
            )
    else:
        for repo in repos:
            short = repo_slice_prefix(repo)
            owned_targets = [item["raw"] for item in target_index[repo]]
            owned_patterns = [item["relative"] for item in target_index[repo]]
            linked_tests = [item["raw"] for item in analysis["test_index"].get(repo, [])]
            linked_test_patterns = [item["relative"] for item in analysis["test_index"].get(repo, [])]
            slices.append(
                {
                    "name": f"{short}-main",
                    "repo": repo,
                    "repo_path": str(repo_root(repo).resolve()),
                    "branch": f"feat/{slug}-{short}-main",
                    "worktree": str((worktree_root / f"{repo}-{slug}-{short}-main").resolve()),
                    "owned_targets": owned_targets,
                    "owned_patterns": owned_patterns,
                    "linked_tests": linked_tests,
                    "linked_test_patterns": linked_test_patterns,
                    "status": "slice-ready",
                }
            )

    plan_payload = {
        "feature": slug,
        "spec_path": rel(spec_path),
        "created_at": utc_now(),
        "worktree_root": str(worktree_root.resolve()),
        "slice_governance": {
            "single_slice_reason": str(analysis.get("single_slice_reason", "")).strip(),
            "multi_domain": bool(analysis.get("multi_domain", False)),
            "phases": [str(item).strip() for item in analysis.get("phases", []) if str(item).strip()],
        },
        "slices": slices,
    }

    plan_json = plan_root / f"{slug}.json"
    plan_md = plan_root / f"{slug}.md"
    plan_json.write_text(json.dumps(plan_payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    lines = [
        f"# Plan for {slug}",
        "",
        f"- Spec: `{rel(spec_path)}`",
        f"- Worktree root: `{worktree_root}`",
        "",
        "| Slice | Repo | Branch | Worktree | Estado |",
        "| --- | --- | --- | --- | --- |",
    ]
    for slice_payload in slices:
        lines.append(
            f"| `{slice_payload['name']}` | `{slice_payload['repo']}` | "
            f"`{slice_payload['branch']}` | `{slice_payload['worktree']}` | "
            f"`{slice_payload['status']}` |"
        )
    lines.extend(
        [
            "",
            "## Hot files",
            "",
            "- Congelar archivos compartidos antes de paralelizar slices del mismo repo.",
            "- Si dos slices comparten los mismos `targets`, mantener ejecucion serial.",
        ]
    )
    plan_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    state = read_state(slug)
    state.update(
        {
            "feature": slug,
            "spec_path": rel(spec_path),
            "status": "planned",
            "repos": repos,
            "plan_json": rel(plan_json),
            "plan_markdown": rel(plan_md),
        }
    )
    write_state(slug, state)

    print(rel(plan_json))
    print(rel(plan_md))
    return 0


def command_slice_start(
    args,
    *,
    slugify: Callable[[str], str],
    load_plan_and_slice: Callable[[str, str], tuple[dict[str, object], dict[str, object], Path]],
    worktree_root: Path,
    report_root: Path,
    read_state: Callable[[str], dict[str, object]],
    write_state: Callable[[str, dict[str, object]], None],
    rel: Callable[[Path], str],
) -> int:
    slug = slugify(args.spec)
    _, selected, _ = load_plan_and_slice(slug, args.slice)

    repo_path = Path(str(selected["repo_path"]))
    worktree = Path(str(selected["worktree"]))
    branch = str(selected["branch"])
    worktree_root.mkdir(parents=True, exist_ok=True)
    add_command_args = [
        "git",
        "-C",
        str(repo_path),
        "worktree",
        "add",
        "--relative-paths",
        str(worktree),
        "-b",
        branch,
    ]
    repair_command_args = [
        "git",
        "-C",
        str(repo_path),
        "worktree",
        "repair",
        "--relative-paths",
        str(worktree),
    ]
    command = " ".join(shlex.quote(part) for part in add_command_args)

    if not worktree.exists():
        execution = subprocess.run(add_command_args, capture_output=True, text=True, check=False)
        if execution.returncode != 0:
            detail = execution.stderr.strip() or execution.stdout.strip() or "git worktree add fallo sin detalle."
            raise SystemExit(f"No se pudo materializar la slice `{args.slice}`:\n- {detail}")
    else:
        repair = subprocess.run(repair_command_args, capture_output=True, text=True, check=False)
        if repair.returncode != 0:
            detail = repair.stderr.strip() or repair.stdout.strip() or "git worktree repair fallo sin detalle."
            raise SystemExit(f"No se pudo reparar la slice `{args.slice}` con rutas relativas:\n- {detail}")

    handoff_path = report_root / f"{slug}-{args.slice}-handoff.md"
    acceptable_evidence = [str(item).strip() for item in selected.get("acceptable_evidence", []) if str(item).strip()]
    minimum_valid_completion = str(selected.get("minimum_valid_completion", "")).strip() or "No declarado."
    handoff = textwrap.dedent(
        f"""\
        # Slice Handoff

        - Feature: `{slug}`
        - Slice: `{args.slice}`
        - Repo: `{selected['repo']}`
        - Branch: `{branch}`
        - Worktree: `{worktree}`

        ## Owned targets

        {chr(10).join(f"- `{target}`" for target in selected['owned_targets'])}

        ## Linked tests

        {chr(10).join(f"- `{target}`" for target in selected.get('linked_tests', [])) or '- Ninguno declarado.'}

        ## Execution contract

        - Executor mode: `{selected.get('executor_mode', 'implementation')}`
        - Slice mode: `{selected.get('slice_mode', 'implementation-heavy')}`
        - Surface policy: `{selected.get('surface_policy', 'required')}`
        - Minimum valid completion: {minimum_valid_completion}
        - Validated no-op allowed: `{'yes' if bool(selected.get('validated_noop_allowed', False)) else 'no'}`
        - Acceptable evidence:
        {chr(10).join(f"- `{item}`" for item in acceptable_evidence) or '- Ninguna declarada.'}
        - Closeout rule: {str(selected.get('closeout_rule', '')).strip() or 'Implementar y verificar segun la spec.'}

        ## Command

        ```bash
        {command}
        ```

        ## Repo Runtime Command

        Para tests unitarios, linters o cualquier comando del runtime del repo, usa el servicio del repo y el worktree de esta slice:

        ```bash
        python3 ./flow repo exec {selected['repo']} --workdir {worktree} -- <cmd>
        ```
        """
    )
    handoff_path.write_text(handoff, encoding="utf-8")

    state = read_state(slug)
    state["status"] = "slice-started"
    slice_results = state.get("slice_results")
    if not isinstance(slice_results, dict):
        slice_results = {}
        state["slice_results"] = slice_results
    slice_results[args.slice] = {
        "status": "started",
        "handoff": rel(handoff_path),
        "repo": str(selected["repo"]),
    }
    write_state(slug, state)

    print(command)
    print(rel(handoff_path))
    return 0


def command_slice_verify(
    args,
    *,
    slugify: Callable[[str], str],
    load_plan_and_slice: Callable[[str, str], tuple[dict[str, object], dict[str, object], Path]],
    root: Path,
    analyze_spec: Callable[[Path], dict[str, object]],
    root_repo: str,
    classify_routed_path: Callable[[str], tuple[str, str]],
    validate_test_reference_patterns: Callable[[str, Path, list[str]], tuple[list[str], list[str], list[str]]],
    git_changed_files: Callable[[Path], tuple[list[str], Optional[str]]],
    detect_test_command: Callable[[str, Path, list[str]], Optional[list[str]]],
    format_findings: Callable[[list[str]], list[str]],
    report_root: Path,
    read_state: Callable[[str], dict[str, object]],
    write_state: Callable[[str, dict[str, object]], None],
    running_inside_workspace: Callable[[], bool],
    repo_compose_service: Callable[[str], str],
    run_workspace_tool: Callable[[list[str], Optional[bool], Optional[str]], int],
    workspace_flow_workdir: Callable[[], str],
    runtime_path: Callable[[Path], Path],
    host_root_hint: Callable[[], str],
    rel: Callable[[Path], str],
    utc_now: Callable[[], str],
) -> int:
    slug = slugify(args.spec)
    plan, selected, _ = load_plan_and_slice(slug, args.slice)
    spec_path = root / str(plan["spec_path"])
    analysis = analyze_spec(spec_path)
    repo_name = str(selected["repo"])

    if (
        not running_inside_workspace()
        and repo_compose_service(repo_name).strip()
        and os.environ.get("FLOW_DELEGATED_TO_WORKSPACE") != "1"
    ):
        delegated_command = [
            "env",
            "FLOW_DELEGATED_TO_WORKSPACE=1",
            f"FLOW_HOST_ROOT={host_root_hint()}",
            "python3",
            "./flow",
            "slice",
            "verify",
            slug,
            args.slice,
        ]
        if bool(getattr(args, "json", False)):
            delegated_command.append("--json")
        return run_workspace_tool(delegated_command, False, workspace_flow_workdir())

    repo_path = runtime_path(Path(str(selected["repo_path"])))
    planned_worktree = runtime_path(Path(str(selected["worktree"])))
    inspection_path = resolve_slice_inspection_path(
        repo_path=repo_path,
        planned_worktree=planned_worktree,
        root=root,
    )

    findings: list[str] = []
    checks: list[tuple[str, str, str]] = []

    if frontmatter_status_allows_execution(analysis["frontmatter"].get("status")):
        checks.append(("PASS", "Estado de spec", "La spec sigue aprobada."))
    elif frontmatter_status_is_terminal(analysis["frontmatter"].get("status")):
        checks.append(("PASS", "Estado de spec", "La spec ya esta liberada; la verificacion es historica."))
    else:
        findings.append("La spec ya no esta en estado `approved`.")
        checks.append(("FAIL", "Estado de spec", "La spec debe volver a aprobarse antes de verificar slices."))

    if analysis["target_errors"]:
        findings.extend(str(error) for error in analysis["target_errors"])
        checks.append(("FAIL", "Targets", "La spec contiene targets invalidos."))
    else:
        checks.append(("PASS", "Targets", "Todos los targets declarados se enrutan de forma valida."))

    if not planned_worktree.exists():
        checks.append(("WARN", "Worktree", f"No existe el worktree planeado; se inspecciona `{inspection_path}`."))
    else:
        checks.append(("PASS", "Worktree", f"Se inspecciona el worktree `{inspection_path}`."))

    owned_targets = [str(target) for target in selected.get("owned_targets", [])]
    owned_patterns = [str(pattern) for pattern in selected.get("owned_patterns", [])]
    misrouted_targets = [target for target in owned_targets if classify_routed_path(target)[0] != repo_name]
    if misrouted_targets:
        findings.extend(f"El target `{target}` no pertenece a la slice `{args.slice}`." for target in misrouted_targets)
        checks.append(("FAIL", "Ownership", "Hay targets de otro repo dentro de la slice."))
    else:
        checks.append(("PASS", "Ownership", "Todos los targets de la slice pertenecen al repo correcto."))

    linked_test_patterns = [str(pattern) for pattern in selected.get("linked_test_patterns", [])]
    if repo_name != root_repo and not linked_test_patterns:
        findings.append(f"La slice `{args.slice}` no tiene referencias `[@test]` para {repo_name}.")
        checks.append(("FAIL", "Test links", "Faltan referencias `[@test]` para esta slice."))
        materialized_tests: list[str] = []
    else:
        materialized_tests, missing_tests, invalid_tests = validate_test_reference_patterns(
            repo_name,
            inspection_path,
            linked_test_patterns,
        )
        if missing_tests:
            findings.extend(
                f"La referencia `[@test] {pattern}` no existe en `{inspection_path}`." for pattern in missing_tests
            )
            checks.append(("FAIL", "Test links", "Hay referencias `[@test]` que no resuelven a archivos reales."))
        elif invalid_tests:
            findings.extend(invalid_tests)
            checks.append(("FAIL", "Test links", "Hay referencias `[@test]` que no son ejecutables por el runner."))
        elif linked_test_patterns:
            checks.append(
                ("PASS", "Test links", f"Las referencias `[@test]` resuelven a {len(materialized_tests)} ruta(s).")
            )
        else:
            checks.append(("WARN", "Test links", "No se requieren `[@test]` para esta slice del workspace."))

    changed_files, git_error = git_changed_files(inspection_path)
    if git_error:
        checks.append(("WARN", "Git diff", f"No se pudo inspeccionar cambios: {git_error}."))
    elif not changed_files:
        checks.append(("WARN", "Git diff", "No hay cambios locales detectados en el repo inspeccionado."))
    else:
        allowed_patterns = owned_patterns + linked_test_patterns
        unexpected_changes = [path for path in changed_files if not matches_any_pattern(path, allowed_patterns)]
        if unexpected_changes:
            findings.extend(
                f"El archivo cambiado `{path}` cae fuera de los targets o tests declarados."
                for path in unexpected_changes
            )
            checks.append(("FAIL", "Git diff", "Hay cambios fuera del alcance declarado por la slice."))
        else:
            checks.append(
                (
                    "PASS",
                    "Git diff",
                    f"Los {len(changed_files)} cambio(s) detectados permanecen dentro del alcance declarado.",
                )
            )

    test_command = detect_test_command(repo_name, inspection_path, materialized_tests)
    test_output = ""
    if test_command:
        test_result = subprocess.run(
            test_command,
            cwd=inspection_path,
            capture_output=True,
            text=True,
            check=False,
        )
        combined_output = (test_result.stdout + "\n" + test_result.stderr).strip()
        test_output = "\n".join(combined_output.splitlines()[-20:])
        if test_result.returncode == 0:
            checks.append(("PASS", "Test runner", "Los tests enlazados pasaron con el runner detectado."))
        else:
            findings.append("El runner detectado devolvio un error al ejecutar los tests enlazados.")
            checks.append(("FAIL", "Test runner", f"El comando fallo: {' '.join(test_command)}"))
    elif materialized_tests:
        checks.append(("WARN", "Test runner", "No se detecto un runner automatico para ejecutar los tests enlazados."))
    else:
        checks.append(("WARN", "Test runner", "No hay tests materializados para ejecutar automaticamente."))

    has_failures = any(status == "FAIL" for status, _, _ in checks)
    report_path = report_root / f"{slug}-{args.slice}-verification.md"
    report = textwrap.dedent(
        f"""\
        # Slice Verification

        - Feature: `{slug}`
        - Slice: `{args.slice}`
        - Repo: `{repo_name}`
        - Ruta inspeccionada: `{inspection_path}`

        ## Checks

        {chr(10).join(f"- [{status}] **{name}**: {detail}" for status, name, detail in checks)}

        ## Findings

        {chr(10).join(format_findings(findings))}

        ## Changed files

        {chr(10).join(f"- `{path}`" for path in changed_files) or '- Ninguno detectado.'}

        ## Linked tests

        {chr(10).join(f"- `{path}`" for path in materialized_tests) or '- Ninguno materializado.'}

        ## Test command

        ```bash
        {' '.join(shlex.quote(part) for part in test_command) if test_command else '# no test runner auto-detectado'}
        ```
        """
    )
    if test_output:
        report += f"\n## Test output\n\n```text\n{test_output}\n```\n"

    report_path.write_text(report, encoding="utf-8")

    state = read_state(slug)
    state["status"] = "in-review" if not has_failures else "implementing"
    state["last_verification_report"] = rel(report_path)
    state["last_verification_result"] = "passed" if not has_failures else "failed"
    slice_results = state.get("slice_results")
    if not isinstance(slice_results, dict):
        slice_results = {}
        state["slice_results"] = slice_results
    slice_results[args.slice] = {
        "status": "passed" if not has_failures else "failed",
        "report": rel(report_path),
        "repo": repo_name,
        "verified_at": utc_now(),
    }
    write_state(slug, state)
    print(rel(report_path))
    return 1 if has_failures else 0


def command_status(
    args,
    *,
    slugify: Callable[[str], str],
    state_root: Path,
    read_state: Callable[[str], dict[str, object]],
    json_dumps: Callable[[object], str],
    workspace_root: Path,
) -> int:
    def read_registry_state(spec_slug: str) -> dict[str, object] | None:
        db_path = workspace_root / "gateway" / "data" / "tasks.db"
        if not db_path.is_file():
            return None
        try:
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                row = connection.execute(
                    """
                    SELECT spec_id, state, assignee, lock_token, lock_expires_at, created_at, updated_at
                    FROM spec_registry
                    WHERE spec_id = ?
                    """,
                    (spec_slug,),
                ).fetchone()
        except sqlite3.Error:
            return None
        if row is None:
            return None
        return {
            "slug": row["spec_id"],
            "feature": row["spec_id"],
            "status": row["state"],
            "assignee": row["assignee"],
            "lock_token": row["lock_token"],
            "lock_expires_at": row["lock_expires_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "source_of_truth": "spec_registry",
        }

    if args.spec:
        slug = slugify(args.spec)
        registry_state = read_registry_state(slug)
        if registry_state is not None:
            print(json_dumps(registry_state))
            return 0
        state = read_state(slug)
        if not state:
            raise SystemExit(f"No existe estado para '{slug}'.")
        print(json_dumps(state))
        return 0

    states = sorted(state_root.glob("*.json"))
    if not states:
        if bool(getattr(args, "json", False)):
            print(json_dumps({"items": []}))
        else:
            print("No hay features registradas en .flow/state.")
        return 0

    items: list[dict[str, object]] = []
    for state_file in states:
        payload = json.loads(state_file.read_text(encoding="utf-8"))
        items.append(payload)
    if bool(getattr(args, "json", False)):
        print(json_dumps({"items": items}))
        return 0

    for payload in items:
        print(
            f"- {payload.get('feature', payload.get('slug', 'unknown'))}: "
            f"{payload.get('status', 'unknown')} "
            f"({payload.get('spec_path', 'sin spec')})"
        )
    return 0
