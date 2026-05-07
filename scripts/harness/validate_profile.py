#!/usr/bin/env python3
"""Validate SoftOS Harness Core + profile separation.

This is intentionally stdlib-only so it can run before project dependencies are
installed. It validates structure and catches obvious leakage of project-private
terms into the reusable core policy pack.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REQUIRED_CORE_FILES = [
    "README.md",
    "lifecycle.md",
    "gates.md",
    "independent-review.md",
    "evidence.md",
    "progress-and-communication.md",
    "pr-readiness.md",
    "automation.md",
    "usage-and-cost.md",
]

REQUIRED_PROFILE_KEYS = [
    "schema_version",
    "profile_id",
    "extends",
    "work_item",
    "repo_mirror",
    "pull_request",
    "reviews",
    "validation",
    "communication",
    "automation",
    "usage_telemetry",
]

REQUIRED_GATES = {"R1", "R2", "R3", "R4", "R5"}

# These are allowed in profiles but should not appear in reusable core docs.
CORE_FORBIDDEN_TERMS = [
    "company-internal",
    "internal-repo",
    "private-ticket-",
    "private-slack",
    "private-postman-workspace",
    "customer-data-example",
]


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # pragma: no cover - user-facing CLI guard
        raise SystemExit(f"invalid JSON in {path}: {exc}") from exc


def validate_core(root: Path) -> list[str]:
    errors: list[str] = []
    core = root / "policies" / "harness-core"
    if not core.is_dir():
        return [f"missing core directory: {core}"]
    for name in REQUIRED_CORE_FILES:
        path = core / name
        if not path.is_file():
            errors.append(f"missing core policy: {path}")
            continue
        text = path.read_text(errors="replace")
        lowered = text.lower()
        for term in CORE_FORBIDDEN_TERMS:
            if term.lower() in lowered:
                errors.append(f"core policy leaks profile-specific term {term!r}: {path}")
    return errors


def discover_profiles(root: Path) -> list[str]:
    profiles_dir = root / "profiles"
    if not profiles_dir.is_dir():
        return []
    return sorted(
        path.parent.name
        for path in profiles_dir.glob("*/profile.json")
        if path.is_file()
    )


def validate_usage_telemetry(profile_id: str, profile: dict) -> list[str]:
    errors: list[str] = []
    usage = profile.get("usage_telemetry", {})
    if usage.get("enabled") is not True:
        errors.append(f"profile {profile_id} must set usage_telemetry.enabled=true")
    if usage.get("report_in_progress_updates") is not True:
        errors.append(f"profile {profile_id} must report usage in progress updates")
    if usage.get("report_in_closeout") is not True:
        errors.append(f"profile {profile_id} must report usage in closeout")
    modes = set(usage.get("modes", []))
    missing_modes = {"exact", "provider_reconciled", "estimated"} - modes
    if missing_modes:
        errors.append(f"profile {profile_id} usage_telemetry missing modes: {sorted(missing_modes)}")
    for key in ["checkpoint_triggers", "dimensions", "progress_update_fields", "final_report_breakdown"]:
        if not usage.get(key):
            errors.append(f"profile {profile_id} usage_telemetry.{key} must be non-empty")
    if usage.get("final_report_required") is not True:
        errors.append(f"profile {profile_id} must require a final usage/cost report")
    budget = usage.get("budget", {})
    if budget.get("enabled") is not True:
        errors.append(f"profile {profile_id} usage_telemetry.budget.enabled must be true")
    if budget.get("warn_at_percent") is None or budget.get("pause_at_percent") is None:
        errors.append(f"profile {profile_id} usage_telemetry.budget must define warn_at_percent and pause_at_percent")
    evidence = usage.get("evidence", {})
    for key in ["default_json_path_template", "default_markdown_path_template"]:
        if not evidence.get(key):
            errors.append(f"profile {profile_id} usage_telemetry.evidence.{key} must be set")
    reconciliation = usage.get("reconciliation", {})
    if reconciliation.get("provider_cost_is_financial_source_of_truth") is not True:
        errors.append(f"profile {profile_id} must identify provider-reconciled cost as financial source of truth")
    return errors


def validate_profile(root: Path, profile_id: str) -> list[str]:
    errors: list[str] = []
    profile_path = root / "profiles" / profile_id / "profile.json"
    if not profile_path.is_file():
        return [f"missing profile: {profile_path}"]
    profile = load_json(profile_path)
    for key in REQUIRED_PROFILE_KEYS:
        if key not in profile:
            errors.append(f"profile {profile_id} missing key: {key}")
    if profile.get("schema_version") != "harness-profile/v1":
        errors.append(f"profile {profile_id} has unsupported schema_version: {profile.get('schema_version')}")
    extends = profile.get("extends")
    if extends != "policies/harness-core":
        errors.append(f"profile {profile_id} must extend policies/harness-core, got {extends!r}")
    gates = set(profile.get("reviews", {}).get("required_gates", []))
    missing = REQUIRED_GATES - gates
    if missing:
        errors.append(f"profile {profile_id} missing required gates: {sorted(missing)}")
    pr = profile.get("pull_request", {})
    if not pr.get("label_discovery") and not pr.get("label_discovery_command"):
        errors.append(f"profile {profile_id} must define label discovery")
    automation = profile.get("automation", {})
    if automation.get("dry_run_first") is not True:
        errors.append(f"profile {profile_id} must set automation.dry_run_first=true")
    communication = profile.get("communication", {})
    if communication.get("ledger_required") is not True:
        errors.append(f"profile {profile_id} must require a communication ledger")
    errors.extend(validate_usage_telemetry(profile_id, profile))
    return errors


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="SoftOS workspace root")
    parser.add_argument("--profile", action="append", default=[], help="Profile id to validate")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    profiles = args.profile or discover_profiles(root)
    errors = validate_core(root)
    if not profiles:
        errors.append(f"no profiles found under {root / 'profiles'}")
    for profile_id in profiles:
        errors.extend(validate_profile(root, profile_id))

    result = {
        "status": "ok" if not errors else "failed",
        "root": str(root),
        "profiles": profiles,
        "errors": errors,
    }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        if errors:
            print("Harness core/profile validation failed:")
            for error in errors:
                print(f"- {error}")
        else:
            print("Harness core/profile validation passed")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
