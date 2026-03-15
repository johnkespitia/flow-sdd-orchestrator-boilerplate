from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional


def render_contract_artifacts(
    slug: str,
    declarations: list[dict[str, object]],
    *,
    generated_contract_root: Path,
    utc_now: Callable[[], str],
    rel: Callable[[Path], str],
    write_json: Callable[[Path, dict[str, object]], None],
    contracts_render_artifacts,
) -> list[dict[str, object]]:
    return contracts_render_artifacts(
        slug,
        declarations,
        generated_contract_root,
        generated_at=utc_now(),
        relativize=rel,
        write_json=write_json,
    )


def verify_contract_declaration(
    declaration: dict[str, object],
    matched_files: list[Path],
    *,
    file_text: Callable[[Path], str],
    contracts_verify_declaration,
) -> list[str]:
    return contracts_verify_declaration(declaration, matched_files, read_text=file_text)


def command_drift_check(
    args,
    *,
    require_dirs: Callable[[], None],
    select_spec_paths,
    root: Path,
    root_repo: str,
    implementation_repos: Callable[[], list[str]],
    repo_root: Callable[[str], Path],
    analyze_spec,
    test_reference_findings: Callable[[dict[str, object]], list[str]],
    git_diff_name_only: Callable[[Path, Optional[str], Optional[str]], tuple[list[str], Optional[str]]],
    repo_paths_changed_under_roots: Callable[[str, list[str]], list[str]],
    matches_any_pattern: Callable[[str, list[str]], bool],
    extract_contract_declarations,
    validate_contract_declaration,
    contract_match_files: Callable[[str, list[str]], list[Path]],
    rel: Callable[[Path], str],
    utc_now: Callable[[], str],
    slugify: Callable[[str], str],
    write_json: Callable[[Path, dict[str, object]], None],
    drift_report_root: Path,
    json_dumps: Callable[[object], str],
    wants_json: Callable[[object], bool],
) -> int:
    require_dirs()
    spec_paths = select_spec_paths(args.spec, all_specs=args.all, changed=args.changed, base=args.base, head=args.head)
    findings: list[str] = []
    items: list[dict[str, object]] = []

    changed_specs: set[Path] = set(spec_paths)
    changed_root_files: list[str] = []
    changed_repo_files: dict[str, list[str]] = {}
    if args.changed:
        changed_root_files, _ = git_diff_name_only(root, base=args.base, head=args.head)
        for repo in implementation_repos():
            changed_repo_files[repo], _ = git_diff_name_only(repo_root(repo), base=args.base, head=args.head)

        if not changed_specs:
            sensitive_changes: list[str] = []
            for repo, paths in changed_repo_files.items():
                sensitive_changes.extend(f"{repo}:{path}" for path in repo_paths_changed_under_roots(repo, paths))
            sensitive_changes.extend(
                f"{root_repo}:{path}" for path in repo_paths_changed_under_roots(root_repo, changed_root_files)
            )
            if sensitive_changes:
                findings.append(
                    "Se detectaron cambios en superficies estables sin cambios de spec: " + ", ".join(sorted(sensitive_changes))
                )

    for spec_path in spec_paths:
        analysis = analyze_spec(spec_path)
        spec_findings: list[str] = []
        for error in analysis["target_errors"]:
            spec_findings.append(str(error))
        for error in analysis["test_errors"]:
            spec_findings.append(str(error))
        spec_findings.extend(test_reference_findings(analysis))

        for repo, entries in analysis["target_index"].items():
            repo_path = repo_root(repo)
            for entry in entries:
                relative = str(entry["relative"])
                candidate = repo_path / relative
                if candidate.exists():
                    continue
                matches = list(repo_path.glob(relative))
                if not matches:
                    spec_findings.append(f"El target `{entry['raw']}` no resuelve a archivos reales.")

        text = str(analysis["text"])
        contracts, contract_errors = extract_contract_declarations(text)
        spec_findings.extend(contract_errors)
        validated_contracts: list[dict[str, object]] = []
        for declaration in contracts:
            normalized, error = validate_contract_declaration(declaration)
            if error:
                spec_findings.append(error)
                continue
            validated_contracts.append(normalized)
            matched_files = contract_match_files(str(normalized["repo"]), list(normalized["match"]))
            if normalized["match"] and not matched_files:
                spec_findings.append(f"Contract `{normalized['name']}` no resolvio archivos con `match`.")
            for token in normalized["contains"]:
                found = False
                for path in matched_files:
                    if token in path.read_text(encoding="utf-8", errors="ignore"):
                        found = True
                        break
                if not found:
                    spec_findings.append(f"Contract `{normalized['name']}` no encontro el token `{token}`.")

        if args.changed:
            covered_changes: list[str] = []
            for repo, paths in changed_repo_files.items():
                covered_patterns = [item["relative"] for item in analysis["target_index"].get(repo, [])]
                for path in repo_paths_changed_under_roots(repo, paths):
                    if covered_patterns and matches_any_pattern(path, covered_patterns):
                        covered_changes.append(f"{repo}:{path}")
            root_patterns = [item["relative"] for item in analysis["target_index"].get(root_repo, [])]
            for path in repo_paths_changed_under_roots(root_repo, changed_root_files):
                if root_patterns and matches_any_pattern(path, root_patterns):
                    covered_changes.append(f"{root_repo}:{path}")
            if not covered_changes and (changed_repo_files or changed_root_files):
                spec_findings.append("La spec cambiada no cubre cambios detectados en superficies estables.")

        items.append(
            {
                "spec": rel(spec_path),
                "contracts": [contract["name"] for contract in validated_contracts],
                "findings": spec_findings,
                "status": "passed" if not spec_findings else "failed",
            }
        )
        findings.extend(f"{rel(spec_path)}: {finding}" for finding in spec_findings)

    report = {
        "generated_at": utc_now(),
        "scope": args.spec or ("changed" if args.changed else "all"),
        "items": items,
        "findings": findings,
    }
    report_path = drift_report_root / f"{slugify(report['scope']) or 'all'}.json"
    write_json(report_path, report)

    if wants_json(args):
        print(json_dumps(report))
        return 1 if findings else 0

    print(rel(report_path))
    for item in items:
        print(f"- {item['spec']}: {item['status']} ({len(item['contracts'])} contracts)")
        for finding in item["findings"]:
            print(f"  finding: {finding}")
    return 1 if findings else 0


def command_contract_verify(
    args,
    *,
    require_dirs: Callable[[], None],
    select_spec_paths,
    spec_slug: Callable[[Path], str],
    extract_contract_declarations,
    validate_contract_declaration,
    contract_match_files: Callable[[str, list[str]], list[Path]],
    render_contract_artifacts,
    verify_contract_declaration,
    rel: Callable[[Path], str],
    utc_now: Callable[[], str],
    slugify: Callable[[str], str],
    write_json: Callable[[Path, dict[str, object]], None],
    contract_report_root: Path,
    json_dumps: Callable[[object], str],
    wants_json: Callable[[object], bool],
    root: Path,
) -> int:
    require_dirs()
    spec_paths = select_spec_paths(args.spec, all_specs=args.all, changed=args.changed, base=args.base, head=args.head)
    findings: list[str] = []
    items: list[dict[str, object]] = []

    for spec_path in spec_paths:
        slug = spec_slug(spec_path)
        text = spec_path.read_text(encoding="utf-8")
        declarations, contract_errors = extract_contract_declarations(text)
        spec_findings = list(contract_errors)
        validated: list[dict[str, object]] = []
        for declaration in declarations:
            normalized, error = validate_contract_declaration(declaration)
            if error:
                spec_findings.append(error)
                continue
            validated.append(normalized)

        artifacts = render_contract_artifacts(slug, validated) if validated else []
        contract_items: list[dict[str, object]] = []
        for declaration in validated:
            matched_files = contract_match_files(str(declaration["repo"]), list(declaration["match"]))
            contract_findings: list[str] = []
            if declaration["match"] and not matched_files:
                contract_findings.append(f"Contract `{declaration['name']}` no resolvio archivos de implementacion.")
            else:
                contract_findings.extend(verify_contract_declaration(declaration, matched_files))
            contract_items.append(
                {
                    "name": declaration["name"],
                    "type": declaration["type"],
                    "repo": declaration["repo"],
                    "artifacts": [artifact["path"] for artifact in artifacts],
                    "matched_files": [rel(path) if root in path.resolve().parents else str(path) for path in matched_files],
                    "status": "passed" if not contract_findings else "failed",
                    "findings": contract_findings,
                }
            )
            spec_findings.extend(contract_findings)

        items.append(
            {
                "spec": rel(spec_path),
                "contracts": contract_items,
                "status": "passed" if not spec_findings else "failed",
                "findings": spec_findings,
            }
        )
        findings.extend(f"{rel(spec_path)}: {finding}" for finding in spec_findings)

    report = {
        "generated_at": utc_now(),
        "scope": args.spec or ("changed" if args.changed else "all"),
        "items": items,
        "findings": findings,
    }
    report_key = slugify(report["scope"]) or "all"
    json_path = contract_report_root / f"{report_key}.json"
    md_path = contract_report_root / f"{report_key}.md"
    write_json(json_path, report)
    lines = [
        "# Contract Verification Report",
        "",
        f"- Scope: `{report['scope']}`",
        f"- Generated at: `{report['generated_at']}`",
        "",
    ]
    for item in items:
        lines.append(f"## {item['spec']}")
        lines.append("")
        lines.append(f"- Status: `{item['status']}`")
        for contract_item in item["contracts"]:
            lines.append(
                f"- Contract `{contract_item['name']}` ({contract_item['type']}/{contract_item['repo']}): "
                f"`{contract_item['status']}`"
            )
            lines.extend(f"- {finding}" for finding in contract_item["findings"] or ["Sin hallazgos."])
        if not item["contracts"]:
            lines.append("- Sin contratos declarados.")
        lines.append("")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    payload = dict(report)
    payload["json_report"] = rel(json_path)
    payload["markdown_report"] = rel(md_path)
    if wants_json(args):
        print(json_dumps(payload))
        return 1 if findings else 0
    print(rel(json_path))
    print(rel(md_path))
    return 1 if findings else 0


def command_spec_generate_contracts(
    args,
    *,
    require_dirs: Callable[[], None],
    resolve_spec: Callable[[str], Path],
    spec_slug: Callable[[Path], str],
    extract_contract_declarations,
    validate_contract_declaration,
    render_contract_artifacts,
    rel: Callable[[Path], str],
    json_dumps: Callable[[object], str],
    wants_json: Callable[[object], bool],
) -> int:
    require_dirs()
    spec_path = resolve_spec(args.spec)
    slug = spec_slug(spec_path)
    text = spec_path.read_text(encoding="utf-8")
    declarations, errors = extract_contract_declarations(text)
    validated: list[dict[str, object]] = []
    for declaration in declarations:
        normalized, error = validate_contract_declaration(declaration)
        if error:
            errors.append(error)
            continue
        validated.append(normalized)

    if errors:
        if wants_json(args):
            print(json_dumps({"spec": rel(spec_path), "artifacts": [], "findings": errors}))
            return 1
        raise SystemExit("\n".join(f"- {error}" for error in errors))

    if not validated:
        payload = {"spec": rel(spec_path), "artifacts": [], "findings": ["No contract declarations found."]}
        if wants_json(args):
            print(json_dumps(payload))
        else:
            print("No contract declarations found.")
        return 0

    artifacts = render_contract_artifacts(slug, validated)
    payload = {"spec": rel(spec_path), "artifacts": artifacts, "findings": []}
    if wants_json(args):
        print(json_dumps(payload))
        return 0

    for artifact in artifacts:
        print(artifact["path"])
    return 0
