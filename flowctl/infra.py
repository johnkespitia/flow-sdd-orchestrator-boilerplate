from __future__ import annotations

import json
from pathlib import Path
from typing import Callable


def command_infra_plan(
    args,
    *,
    require_dirs: Callable[[], None],
    resolve_spec,
    spec_slug: Callable[[Path], str],
    analyze_spec,
    frontmatter_list,
    require_routed_paths,
    load_providers_config,
    select_provider,
    provider_entrypoint_path,
    run_provider,
    rel: Callable[[Path], str],
    utc_now: Callable[[], str],
    write_json,
    infra_report_root: Path,
    json_dumps: Callable[[object], str],
) -> int:
    require_dirs()
    spec_path = resolve_spec(args.spec)
    slug = spec_slug(spec_path)
    analysis = analyze_spec(spec_path)
    infra_targets = frontmatter_list(analysis["frontmatter"], "infra_targets")
    if not infra_targets:
        raise SystemExit(f"La spec `{rel(spec_path)}` no declara `infra_targets`.")

    infra_index = require_routed_paths(infra_targets, "infra targets")
    providers_payload = load_providers_config()
    provider_name, provider_config_payload = select_provider(providers_payload, "infra", explicit=args.provider)
    payload = {
        "generated_at": utc_now(),
        "feature": slug,
        "environment": args.environment,
        "spec_path": rel(spec_path),
        "infra_targets": infra_targets,
        "repos": {repo: [item["relative"] for item in items] for repo, items in infra_index.items()},
        "provider": provider_name,
        "entrypoint": rel(provider_entrypoint_path(provider_config_payload)),
        "status": "planned",
    }

    execution = run_provider(
        "infra",
        "plan",
        provider_name,
        provider_config_payload,
        {
            "FLOW_INFRA_ENV": args.environment,
            "FLOW_INFRA_SPEC": rel(spec_path),
            "FLOW_INFRA_SPEC_PATH": str(spec_path.resolve()),
            "FLOW_INFRA_TARGETS": json.dumps(infra_targets, ensure_ascii=True),
            "FLOW_INFRA_TARGET_REPOS": ",".join(sorted(infra_index)),
        },
    )
    payload["output_tail"] = execution["output_tail"]
    if int(execution["returncode"]) != 0:
        payload["status"] = "failed"

    json_path = infra_report_root / f"{slug}-{args.environment}-plan.json"
    md_path = infra_report_root / f"{slug}-{args.environment}-plan.md"
    write_json(json_path, payload)
    lines = [
        f"# Infra Plan: {slug}",
        "",
        f"- Environment: `{args.environment}`",
        f"- Spec: `{rel(spec_path)}`",
        f"- Provider: `{payload['provider']}`",
        f"- Entrypoint: `{payload['entrypoint']}`",
        "",
        "## Infra targets",
        "",
    ]
    lines.extend([f"- `{target}`" for target in infra_targets])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload["json_report"] = rel(json_path)
    payload["markdown_report"] = rel(md_path)
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
        return 1 if payload["status"] == "failed" else 0
    print(rel(json_path))
    print(rel(md_path))
    return 1 if payload["status"] == "failed" else 0


def command_infra_apply(
    args,
    *,
    slugify: Callable[[str], str],
    infra_report_root: Path,
    load_providers_config,
    select_provider,
    provider_entrypoint_path,
    run_provider,
    rel: Callable[[Path], str],
    utc_now: Callable[[], str],
    write_json,
    json_dumps: Callable[[object], str],
) -> int:
    slug = slugify(args.spec)
    plan_path = infra_report_root / f"{slug}-{args.environment}-plan.json"
    if not plan_path.exists():
        raise SystemExit(
            f"No existe plan para `{slug}` en `{args.environment}`. Ejecuta `python3 ./flow infra plan {slug} --env {args.environment}`."
        )
    if args.environment in {"staging", "production"} and not args.approver:
        raise SystemExit("`--approver` es obligatorio para staging y production.")

    providers_payload = load_providers_config()
    provider_name, provider_config_payload = select_provider(providers_payload, "infra", explicit=args.provider)

    payload = {
        "generated_at": utc_now(),
        "feature": slug,
        "environment": args.environment,
        "plan_path": rel(plan_path),
        "approver": args.approver,
        "provider": provider_name,
        "entrypoint": rel(provider_entrypoint_path(provider_config_payload)),
        "status": "executed",
    }
    execution = run_provider(
        "infra",
        "apply",
        provider_name,
        provider_config_payload,
        {
            "FLOW_INFRA_ENV": args.environment,
            "FLOW_INFRA_PLAN": str(plan_path.resolve()),
            "FLOW_INFRA_APPROVER": args.approver or "",
        },
    )
    payload["output_tail"] = execution["output_tail"]
    if int(execution["returncode"]) != 0:
        payload["status"] = "failed"

    json_path = infra_report_root / f"{slug}-{args.environment}-apply.json"
    md_path = infra_report_root / f"{slug}-{args.environment}-apply.md"
    write_json(json_path, payload)
    md_path.write_text(
        "\n".join(
            [
                f"# Infra Apply: {slug}",
                "",
                f"- Environment: `{args.environment}`",
                f"- Plan: `{rel(plan_path)}`",
                f"- Provider: `{payload['provider']}`",
                f"- Entrypoint: `{payload['entrypoint']}`",
                f"- Status: `{payload['status']}`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    payload["json_report"] = rel(json_path)
    payload["markdown_report"] = rel(md_path)
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
        return 1 if payload["status"] == "failed" else 0
    print(rel(json_path))
    print(rel(md_path))
    return 1 if payload["status"] == "failed" else 0


def command_infra_status(
    args,
    *,
    slugify: Callable[[str], str],
    infra_report_root: Path,
    json_dumps: Callable[[object], str],
) -> int:
    slug = slugify(args.spec)
    plans = sorted(infra_report_root.glob(f"{slug}-*-plan.json"))
    applies = sorted(infra_report_root.glob(f"{slug}-*-apply.json"))
    if not plans and not applies:
        raise SystemExit(f"No existe estado de infra para `{slug}`.")

    items: list[dict[str, object]] = []
    for path in plans + applies:
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["report"] = path.name
        items.append(payload)
    if bool(getattr(args, "json", False)):
        print(json_dumps({"feature": slug, "items": items}))
        return 0
    for payload in items:
        print(f"- {payload.get('report')}: {payload.get('status', 'unknown')} ({payload.get('environment', 'n/a')})")
    return 0
