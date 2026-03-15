from __future__ import annotations

import fnmatch
import json
import shlex
import subprocess
import textwrap
from pathlib import Path
from typing import Callable, Optional


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
    spec_path = feature_specs / f"{slug}.spec.md"
    if spec_path.exists():
        raise SystemExit(f"La spec ya existe: {rel(spec_path)}")

    target_block = render_targets(repos)
    repo_rows = "\n".join(f"| `{repo}` | {', '.join(default_targets[repo])} |" for repo in repos)
    body = "\n".join(
        [
            "---",
            f"name: {title}",
            "description: TODO describir el resultado observable",
            "status: draft",
            "owner: platform",
            "targets:",
            target_block,
            "---",
            "",
            f"# {title}",
            "",
            "## Objetivo",
            "",
            "Describir el comportamiento observable que esta feature debe introducir.",
            "",
            "## Contexto",
            "",
            "- por que existe ahora",
            "- que foundations gobiernan esta feature",
            "- que repos estan afectados",
            "",
            "## Problema a resolver",
            "",
            "- que duele hoy",
            "- que riesgo o ineficiencia se quiere eliminar",
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
            "",
            "## Criterios de aceptacion",
            "",
            "- TODO",
            "- TODO",
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
    format_findings: Callable[[list[str]], list[str]],
    report_root: Path,
    read_state: Callable[[str], dict[str, object]],
    write_state: Callable[[str, dict[str, object]], None],
    rel: Callable[[Path], str],
) -> int:
    require_dirs()
    spec_path = resolve_spec(args.spec)
    slug = spec_slug(spec_path)
    analysis = analyze_spec(spec_path)
    frontmatter = analysis["frontmatter"]

    high_priority: list[str] = []
    medium_priority: list[str] = []
    low_priority: list[str] = []

    for field in analysis["missing_frontmatter"]:
        high_priority.append(f"Falta el campo de frontmatter `{field}`.")

    high_priority.extend(str(error) for error in analysis["target_errors"])
    high_priority.extend(str(error) for error in analysis["test_errors"])

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
        - Targets declarados: `{len(analysis['targets'])}`
        - Referencias `[@test]`: `{len(analysis['test_refs'])}`
        """
    )
    report_path.write_text(report, encoding="utf-8")

    state = read_state(slug)
    state.update(
        {
            "feature": slug,
            "spec_path": rel(spec_path),
            "status": "reviewing-spec",
        }
    )
    write_state(slug, state)
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
) -> int:
    spec_path = resolve_spec(args.spec)
    slug = spec_slug(spec_path)
    analysis = ensure_spec_ready_for_approval(spec_path)
    replace_frontmatter_status(spec_path, "approved")
    state = read_state(slug)
    state.update(
        {
            "feature": slug,
            "title": analysis["frontmatter"].get("name", slug),
            "spec_path": rel(spec_path),
            "status": "approved-spec",
            "repos": list(analysis["target_index"]),
        }
    )
    write_state(slug, state)
    print(f"Spec aprobada: {rel(spec_path)}")
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
    if frontmatter.get("status") != "approved":
        raise SystemExit(f"La spec '{slug}' debe estar en estado `approved` antes de planearla.")

    if analysis["target_errors"]:
        joined = "\n".join(f"- {error}" for error in analysis["target_errors"])
        raise SystemExit(f"La spec tiene targets invalidos:\n{joined}")

    target_index = require_routed_paths(analysis["targets"], "targets")
    repos = list(target_index)

    slices: list[dict[str, object]] = []
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

    repo_path = selected["repo_path"]
    worktree = selected["worktree"]
    branch = selected["branch"]
    worktree_root.mkdir(parents=True, exist_ok=True)
    command = f"git -C {shlex.quote(repo_path)} worktree add {shlex.quote(worktree)} -b {shlex.quote(branch)}"

    handoff_path = report_root / f"{slug}-{args.slice}-handoff.md"
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

        ## Command

        ```bash
        {command}
        ```
        """
    )
    handoff_path.write_text(handoff, encoding="utf-8")

    state = read_state(slug)
    state["status"] = "slice-ready"
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
    rel: Callable[[Path], str],
) -> int:
    slug = slugify(args.spec)
    plan, selected, _ = load_plan_and_slice(slug, args.slice)
    spec_path = root / str(plan["spec_path"])
    analysis = analyze_spec(spec_path)
    repo_name = str(selected["repo"])
    repo_path = Path(str(selected["repo_path"]))
    planned_worktree = Path(str(selected["worktree"]))
    inspection_path = planned_worktree if planned_worktree.exists() else repo_path

    findings: list[str] = []
    checks: list[tuple[str, str, str]] = []

    if analysis["frontmatter"].get("status") == "approved":
        checks.append(("PASS", "Estado de spec", "La spec sigue aprobada."))
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
) -> int:
    if args.spec:
        slug = slugify(args.spec)
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
