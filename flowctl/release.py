from __future__ import annotations

from pathlib import Path
from typing import Callable


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
    root_repo: str,
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
    provider_name, provider_config_payload = select_provider(providers_payload, "release", explicit=args.provider)
    promotion_payload = {
        "version": args.version,
        "environment": args.environment,
        "promoted_at": utc_now(),
        "approver": args.approver,
        "status": "recorded",
        "provider": provider_name,
        "entrypoint": rel(provider_entrypoint_path(provider_config_payload)),
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
