from __future__ import annotations

import json
from pathlib import Path
from typing import Callable


def _repo_deploy_provider(repo_payload: dict[str, object], environment: str) -> str:
    deploy = repo_payload.get("deploy")
    if not isinstance(deploy, dict):
        return ""
    by_env = deploy.get("providers_by_env")
    if isinstance(by_env, dict):
        scoped = str(by_env.get(environment, "")).strip()
        if scoped:
            return scoped
    return str(deploy.get("provider", "")).strip()


def _repo_deploy_env(repo_payload: dict[str, object], environment: str) -> dict[str, str]:
    deploy = repo_payload.get("deploy")
    if not isinstance(deploy, dict):
        return {}
    scoped: dict[str, str] = {}
    by_env = deploy.get("env_by_env")
    if isinstance(by_env, dict):
        raw_env = by_env.get(environment, {})
        if isinstance(raw_env, dict):
            for key, value in raw_env.items():
                scoped[str(key)] = str(value)
    raw_common = deploy.get("env")
    if isinstance(raw_common, dict):
        for key, value in raw_common.items():
            scoped[str(key)] = str(value)
    return scoped


def _resolve_release_provider_from_workspace(
    *,
    args,
    manifest: dict[str, object],
    workspace_config: dict[str, object],
    root_repo: str,
) -> tuple[str, dict[str, str], list[str]]:
    if getattr(args, "provider", None):
        return str(args.provider).strip(), {}, []

    repos_section = workspace_config.get("repos", {})
    if not isinstance(repos_section, dict):
        return "", {}, []

    manifest_repos = manifest.get("repos", {})
    if not isinstance(manifest_repos, dict):
        return "", {}, []

    candidate_repos = [str(repo).strip() for repo in manifest_repos if str(repo).strip()]
    deploy_repo = str(getattr(args, "deploy_repo", "") or "").strip()
    if deploy_repo:
        if deploy_repo not in candidate_repos:
            raise SystemExit(
                f"`--deploy-repo {deploy_repo}` no pertenece al release `{args.version}`."
            )
        candidate_repos = [deploy_repo]

    non_root_candidates = [repo for repo in candidate_repos if repo != root_repo]
    if non_root_candidates:
        candidate_repos = non_root_candidates

    selected: list[tuple[str, str]] = []
    merged_env: dict[str, str] = {}
    for repo in candidate_repos:
        repo_payload = repos_section.get(repo)
        if not isinstance(repo_payload, dict):
            continue
        provider = _repo_deploy_provider(repo_payload, args.environment)
        if not provider:
            continue
        selected.append((repo, provider))
        merged_env.update(_repo_deploy_env(repo_payload, args.environment))

    unique_providers = sorted({provider for _, provider in selected})
    if len(unique_providers) > 1:
        details = ", ".join(f"{repo}:{provider}" for repo, provider in selected)
        raise SystemExit(
            "Hay multiples providers de deploy en el release. "
            f"Usa `--provider` o `--deploy-repo`. Detectados: {details}."
        )
    if len(unique_providers) == 1:
        return unique_providers[0], merged_env, [repo for repo, _ in selected]
    return "", merged_env, []


def _release_slice_findings(
    slug: str,
    state: dict[str, object],
    *,
    plan_root: Path,
    root: Path,
    rel: Callable[[Path], str],
) -> list[str]:
    plan_path = plan_root / f"{slug}.json"
    if not plan_path.exists():
        return [f"No existe plan para `{slug}`. Ejecuta `python3 ./flow plan {slug}` antes del release."]

    try:
        plan_payload = json.loads(plan_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"El plan `{rel(plan_path)}` no contiene JSON valido: {exc}."]

    slices = plan_payload.get("slices", [])
    if not isinstance(slices, list) or not slices:
        return [f"El plan `{rel(plan_path)}` no declara slices verificables."]

    slice_results = state.get("slice_results", {})
    if not isinstance(slice_results, dict):
        slice_results = {}

    findings: list[str] = []
    for slice_payload in slices:
        if not isinstance(slice_payload, dict):
            continue
        slice_name = str(slice_payload.get("name", "")).strip()
        if not slice_name:
            continue
        result = slice_results.get(slice_name)
        if not isinstance(result, dict):
            findings.append(f"La slice `{slice_name}` no tiene verificacion registrada.")
            continue
        if str(result.get("status", "")).strip() != "passed":
            findings.append(f"La slice `{slice_name}` no paso su verificacion mas reciente.")
        report = str(result.get("report", "")).strip()
        if not report:
            findings.append(f"La slice `{slice_name}` no registro un reporte de verificacion.")
            continue
        if not (root / report).exists():
            findings.append(f"La slice `{slice_name}` referencia un reporte inexistente: `{report}`.")
    return findings


def command_release_cut(
    args,
    *,
    require_dirs: Callable[[], None],
    release_default_version: Callable[[], str],
    release_manifest_path: Callable[[str], Path],
    resolve_spec,
    releasable_feature_specs: Callable[[], list[Path]],
    ensure_spec_ready_for_approval,
    rel: Callable[[Path], str],
    spec_slug: Callable[[Path], str],
    read_state,
    root: Path,
    root_repo: str,
    plan_root: Path,
    git_changed_files: Callable[[Path], tuple[list[str], str | None]],
    repo_head_sha: Callable[[str], str],
    repo_root,
    release_manifest_root: Path,
    utc_now: Callable[[], str],
    write_json,
    write_state,
    json_dumps: Callable[[object], str],
) -> int:
    require_dirs()
    version = args.version or release_default_version()
    manifest_path = release_manifest_path(version)
    if manifest_path.exists() and not args.force:
        raise SystemExit(f"Ya existe un manifest para `{version}`. Usa `--force` para regenerarlo.")

    if args.spec:
        spec_paths = [resolve_spec(identifier) for identifier in args.spec]
    elif args.all_approved:
        spec_paths = releasable_feature_specs()
    else:
        raise SystemExit("Debes indicar `--spec` o `--all-approved` para cortar un release.")

    if not spec_paths:
        raise SystemExit("No encontre specs aprobadas para incluir en el release.")

    features: list[dict[str, object]] = []
    repos_involved = {root_repo}

    for spec_path in spec_paths:
        analysis = ensure_spec_ready_for_approval(spec_path)
        if analysis["frontmatter"].get("status") != "approved":
            raise SystemExit(f"La spec `{rel(spec_path)}` debe estar en `approved` para entrar en un release.")
        repos = sorted(analysis["target_index"])
        repos_involved.update(repos)
        slug = spec_slug(spec_path)
        state = read_state(slug)
        slice_findings = _release_slice_findings(
            slug,
            state,
            plan_root=plan_root,
            root=root,
            rel=rel,
        )
        if slice_findings:
            joined = "\n".join(f"- {finding}" for finding in slice_findings)
            raise SystemExit(f"La feature `{slug}` no esta lista para release:\n{joined}")
        features.append(
            {
                "slug": slug,
                "spec_path": rel(spec_path),
                "state_status": state.get("status", "unknown"),
                "repos": repos,
                "targets": analysis["targets"],
                "test_refs": analysis["test_refs"],
            }
        )

    dirty_repo_findings: list[str] = []
    for repo in sorted(repos_involved):
        changed_files, git_error = git_changed_files(repo_root(repo))
        if git_error:
            dirty_repo_findings.append(f"No pude inspeccionar cambios locales de `{repo}`: {git_error}")
            continue
        if not changed_files:
            continue
        preview = ", ".join(f"`{path}`" for path in changed_files[:5])
        suffix = " ..." if len(changed_files) > 5 else ""
        dirty_repo_findings.append(f"`{repo}` tiene cambios sin commit: {preview}{suffix}")
    if dirty_repo_findings:
        joined = "\n".join(f"- {finding}" for finding in dirty_repo_findings)
        raise SystemExit(f"No puedo cortar un release con cambios locales sin commit:\n{joined}")

    manifest = {
        "version": version,
        "generated_at": utc_now(),
        "root_sha": repo_head_sha(root_repo),
        "repos": {
            repo: {
                "path": str(repo_root(repo)),
                "sha": repo_head_sha(repo),
            }
            for repo in sorted(repos_involved)
        },
        "features": features,
        "promotions": [],
    }
    write_json(manifest_path, manifest)

    summary_path = release_manifest_root / f"{version}.md"
    lines = [
        f"# Release Manifest {version}",
        "",
        f"- Root SHA: `{manifest['root_sha']}`",
        "",
        "## Repos",
        "",
    ]
    for repo, payload in manifest["repos"].items():
        lines.append(f"- `{repo}`: `{payload['sha']}`")
    lines.extend(["", "## Features", ""])
    for feature in features:
        lines.append(
            f"- `{feature['slug']}`: `{feature['state_status']}` "
            f"({', '.join(feature['repos'])})"
        )
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    for feature in features:
        state = read_state(feature["slug"])
        if state:
            state["release_candidate"] = version
            if "created_at" not in state:
                state["created_at"] = utc_now()
            write_state(feature["slug"], state)

    payload = {
        "version": version,
        "manifest": rel(manifest_path),
        "summary": rel(summary_path),
        "features": [feature["slug"] for feature in features],
        "repos": sorted(repos_involved),
    }
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
        return 0
    print(rel(manifest_path))
    print(rel(summary_path))
    return 0


def command_release_manifest(
    args,
    *,
    load_release_manifest,
    release_manifest_path: Callable[[str], Path],
    rel: Callable[[Path], str],
    json_dumps: Callable[[object], str],
) -> int:
    manifest = load_release_manifest(args.version)
    if bool(getattr(args, "json", False)):
        print(json_dumps(manifest))
        return 0
    print(rel(release_manifest_path(args.version)))
    return 0


def command_release_status(
    args,
    *,
    load_release_manifest,
    json_dumps: Callable[[object], str],
) -> int:
    manifest = load_release_manifest(args.version)
    payload = {
        "version": manifest.get("version"),
        "root_sha": manifest.get("root_sha"),
        "features": manifest.get("features", []),
        "promotions": manifest.get("promotions", []),
    }
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
        return 0
    print(f"- version: {manifest.get('version')}")
    print(f"- root_sha: {manifest.get('root_sha')}")
    print(f"- features: {len(manifest.get('features', []))}")
    promotions = manifest.get("promotions", [])
    if promotions:
        for promotion in promotions:
            print(
                f"- promotion {promotion.get('environment')}: "
                f"{promotion.get('status')} at {promotion.get('promoted_at')}"
            )
    else:
        print("- promotions: none")
    return 0


def command_release_promote(
    args,
    *,
    load_release_manifest,
    workspace_config: dict[str, object],
    root_repo: str,
    load_providers_config,
    select_provider,
    provider_entrypoint_path,
    run_provider,
    release_manifest_path: Callable[[str], Path],
    release_promotion_path: Callable[[str, str], Path],
    rel: Callable[[Path], str],
    utc_now: Callable[[], str],
    write_json,
    read_state,
    write_state,
    json_dumps: Callable[[object], str],
) -> int:
    manifest = load_release_manifest(args.version)
    if args.environment in {"staging", "production"} and not args.approver:
        raise SystemExit("`--approver` es obligatorio para staging y production.")

    providers_payload = load_providers_config()
    inferred_provider, deploy_env, provider_repos = _resolve_release_provider_from_workspace(
        args=args,
        manifest=manifest,
        workspace_config=workspace_config,
        root_repo=root_repo,
    )
    explicit_provider = str(getattr(args, "provider", "") or "").strip() or inferred_provider or None
    provider_name, provider_config_payload = select_provider(providers_payload, "release", explicit=explicit_provider)
    promotion_payload = {
        "version": args.version,
        "environment": args.environment,
        "promoted_at": utc_now(),
        "approver": args.approver,
        "status": "recorded",
        "provider": provider_name,
        "entrypoint": rel(provider_entrypoint_path(provider_config_payload)),
    }
    if inferred_provider:
        promotion_payload["provider_resolution"] = {
            "mode": "workspace-deploy",
            "repos": provider_repos,
        }

    execution = run_provider(
        "release",
        "promote",
        provider_name,
        provider_config_payload,
        {
            "FLOW_RELEASE_VERSION": args.version,
            "FLOW_RELEASE_ENV": args.environment,
            "FLOW_RELEASE_MANIFEST": str(release_manifest_path(args.version).resolve()),
            "FLOW_RELEASE_APPROVER": args.approver or "",
            **deploy_env,
        },
    )
    promotion_payload["output_tail"] = execution["output_tail"]
    if int(execution["returncode"]) != 0:
        promotion_payload["status"] = "failed"
        write_json(release_promotion_path(args.version, args.environment), promotion_payload)
        raise SystemExit(
            f"La promocion `{args.environment}` fallo con `{execution['provider']}` ({execution['entrypoint']})."
        )

    promotion_payload["status"] = "executed"

    promotions = manifest.setdefault("promotions", [])
    if isinstance(promotions, list):
        promotions.append(promotion_payload)
    write_json(release_manifest_path(args.version), manifest)
    write_json(release_promotion_path(args.version, args.environment), promotion_payload)

    if args.environment == "production":
        for feature in manifest.get("features", []):
            slug = str(feature.get("slug", ""))
            if not slug:
                continue
            state = read_state(slug)
            if not state:
                continue
            state["status"] = "released"
            state["released_in"] = args.version
            write_state(slug, state)
    promotion_path = rel(release_promotion_path(args.version, args.environment))
    if bool(getattr(args, "json", False)):
        promotion_payload["path"] = promotion_path
        print(json_dumps(promotion_payload))
        return 0
    print(promotion_path)
    return 0
