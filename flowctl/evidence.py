from __future__ import annotations

import json
import shutil
import textwrap
from pathlib import Path
from typing import Callable

from flowctl.features import plan_approval_status_payload, spec_approval_status_payload
from flowctl.policy import policy_check_payload


def _read_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _report_kind(report_root: Path, path: Path) -> str:
    try:
        relative = path.relative_to(report_root)
    except ValueError:
        return "unknown"
    return relative.parts[0] if len(relative.parts) > 1 else "root"


def _matching_reports(*, report_root: Path, slug: str, rel: Callable[[Path], str]) -> list[dict[str, object]]:
    if not report_root.exists():
        return []
    reports: list[dict[str, object]] = []
    for path in sorted(report_root.rglob("*")):
        if not path.is_file() or slug not in path.name or path.suffix not in {".json", ".md"}:
            continue
        item: dict[str, object] = {
            "path": rel(path),
            "kind": _report_kind(report_root, path),
            "format": path.suffix.lstrip("."),
            "size_bytes": path.stat().st_size,
            "mtime_ns": path.stat().st_mtime_ns,
        }
        if item["kind"] in {"evidence", "agent-handoffs"}:
            continue
        if path.suffix == ".json":
            payload = _read_json(path)
            for key in ("status", "engine_status", "scope", "generated_at", "json_report"):
                if key in payload:
                    item[key] = payload[key]
            items = payload.get("items")
            if isinstance(items, list) and items:
                first = items[0]
                if isinstance(first, dict) and "status" in first:
                    item["item_status"] = first["status"]
        reports.append(item)
    return reports


def evidence_status_payload(
    *,
    slug: str,
    spec_path: Path,
    plan_path: Path,
    state: dict[str, object],
    report_root: Path,
    rel: Callable[[Path], str],
    utc_now: Callable[[], str],
) -> dict[str, object]:
    spec_status = spec_approval_status_payload(spec_path=spec_path, slug=slug, state=state, rel=rel)
    plan_status = plan_approval_status_payload(
        slug=slug,
        spec_path=spec_path,
        plan_path=plan_path,
        state=state,
        rel=rel,
    )
    policies = {
        stage: policy_check_payload(
            stage=stage,
            slug=slug,
            spec_path=spec_path,
            plan_path=plan_path,
            state=state,
            rel=rel,
        )
        for stage in ("plan", "slice-start", "workflow-run", "release")
    }
    reports = _matching_reports(report_root=report_root, slug=slug, rel=rel)
    ci_spec_reports = [
        report
        for report in reports
        if report.get("kind") == "ci" and str(report.get("path", "")).endswith(".json")
    ]
    workflow_reports = [
        report
        for report in reports
        if report.get("kind") == "workflows" and str(report.get("path", "")).endswith(".json")
    ]
    ci_spec_passed = any(report.get("item_status") == "passed" or report.get("status") == "passed" for report in ci_spec_reports)
    workflow_statuses = [str(report.get("status", "") or report.get("engine_status", "") or "") for report in workflow_reports]
    release_policy_allowed = bool(policies["release"].get("allowed"))
    ready_for_release = bool(
        spec_status.get("approved")
        and plan_status.get("approved")
        and release_policy_allowed
        and ci_spec_passed
        and reports
    )
    missing: list[str] = []
    if not spec_status.get("approved"):
        missing.append("spec_approval")
    if not plan_status.get("approved"):
        missing.append("plan_approval")
    if not release_policy_allowed:
        missing.append("release_policy")
    if not ci_spec_passed:
        missing.append("ci_spec_passed")
    if not reports:
        missing.append("reports")
    return {
        "feature": slug,
        "generated_at": utc_now(),
        "spec_path": rel(spec_path),
        "plan_path": rel(plan_path),
        "ready_for_release": ready_for_release,
        "missing": missing,
        "spec_approval": spec_status,
        "plan_approval": plan_status,
        "policies": policies,
        "state": {
            "status": state.get("status"),
            "last_review": state.get("last_review"),
            "last_verification_result": state.get("last_verification_result"),
            "workflow_engine": state.get("workflow_engine"),
            "slice_results": state.get("slice_results"),
        },
        "reports": reports,
        "ci_spec": {
            "passed": ci_spec_passed,
            "reports": ci_spec_reports,
        },
        "workflow": {
            "statuses": [status for status in workflow_statuses if status],
            "reports": workflow_reports,
        },
    }


def write_evidence_bundle(
    *,
    payload: dict[str, object],
    evidence_report_root: Path,
    root: Path,
    rel: Callable[[Path], str],
) -> dict[str, object]:
    slug = str(payload["feature"])
    bundle_root = evidence_report_root / slug
    bundle_root.mkdir(parents=True, exist_ok=True)
    bundle_json = evidence_report_root / f"{slug}-evidence-bundle.json"
    bundle_md = evidence_report_root / f"{slug}-evidence-bundle.md"
    bundled_files: list[dict[str, object]] = []
    for report in payload.get("reports", []):
        if not isinstance(report, dict):
            continue
        source = root / str(report.get("path", ""))
        if not source.is_file():
            continue
        destination = bundle_root / source.name
        shutil.copy2(source, destination)
        bundled_files.append({"source": rel(source), "bundle_path": rel(destination)})
    bundle_payload = dict(payload)
    bundle_payload["bundle"] = {
        "json_report": rel(bundle_json),
        "markdown_report": rel(bundle_md),
        "files_root": rel(bundle_root),
        "files": bundled_files,
    }
    bundle_json.write_text(json.dumps(bundle_payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    missing_lines = "\n".join(f"- `{item}`" for item in bundle_payload["missing"]) or "- none"
    report_lines = "\n".join(f"- `{item['path']}` ({item['kind']}/{item['format']})" for item in bundle_payload["reports"]) or "- none"
    bundle_md.write_text(
        textwrap.dedent(
            f"""\
            # Evidence Bundle: {slug}

            - Ready for release: `{'yes' if bundle_payload['ready_for_release'] else 'no'}`
            - Spec: `{bundle_payload['spec_path']}`
            - Plan: `{bundle_payload['plan_path']}`

            ## Missing

            {missing_lines}

            ## Reports

            {report_lines}
            """
        ),
        encoding="utf-8",
    )
    return bundle_payload


def command_evidence_status(
    args,
    *,
    resolve_spec: Callable[[str], Path],
    spec_slug: Callable[[Path], str],
    plan_root: Path,
    report_root: Path,
    read_state: Callable[[str], dict[str, object]],
    rel: Callable[[Path], str],
    utc_now: Callable[[], str],
    json_dumps: Callable[[object], str],
) -> int:
    spec_path = resolve_spec(args.spec)
    slug = spec_slug(spec_path)
    payload = evidence_status_payload(
        slug=slug,
        spec_path=spec_path,
        plan_path=plan_root / f"{slug}.json",
        state=read_state(slug),
        report_root=report_root,
        rel=rel,
        utc_now=utc_now,
    )
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
    else:
        print(f"Evidence status: {'ready' if payload['ready_for_release'] else 'not-ready'}")
        if payload["missing"]:
            print("Missing:")
            for item in payload["missing"]:
                print(f"- {item}")
    return 0 if bool(payload["ready_for_release"]) else 2


def command_evidence_bundle(
    args,
    *,
    root: Path,
    resolve_spec: Callable[[str], Path],
    spec_slug: Callable[[Path], str],
    plan_root: Path,
    report_root: Path,
    evidence_report_root: Path,
    read_state: Callable[[str], dict[str, object]],
    rel: Callable[[Path], str],
    utc_now: Callable[[], str],
    json_dumps: Callable[[object], str],
) -> int:
    spec_path = resolve_spec(args.spec)
    slug = spec_slug(spec_path)
    payload = evidence_status_payload(
        slug=slug,
        spec_path=spec_path,
        plan_path=plan_root / f"{slug}.json",
        state=read_state(slug),
        report_root=report_root,
        rel=rel,
        utc_now=utc_now,
    )
    bundle_payload = write_evidence_bundle(
        payload=payload,
        evidence_report_root=evidence_report_root,
        root=root,
        rel=rel,
    )
    if bool(getattr(args, "json", False)):
        print(json_dumps(bundle_payload))
    else:
        bundle = bundle_payload["bundle"]
        if isinstance(bundle, dict):
            print(bundle["json_report"])
            print(bundle["markdown_report"])
    return 0 if bool(bundle_payload["ready_for_release"]) else 2
