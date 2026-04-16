from __future__ import annotations

from pathlib import Path
from typing import Callable

from flowctl.features import plan_approval_status_payload, spec_approval_status_payload


POLICY_STAGES = ("plan", "slice-start", "workflow-run", "release")
_STAGE_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "plan": ("spec_approval",),
    "slice-start": ("spec_approval", "plan_approval"),
    "workflow-run": ("spec_approval", "plan_approval"),
    "release": ("spec_approval", "plan_approval"),
}


def normalize_stage(stage: str) -> str:
    normalized = stage.strip().replace("_", "-")
    if normalized not in _STAGE_REQUIREMENTS:
        valid = ", ".join(POLICY_STAGES)
        raise SystemExit(f"Stage de policy invalido `{stage}`. Valores validos: {valid}.")
    return normalized


def _check_payload(
    *,
    name: str,
    required: bool,
    status: dict[str, object],
) -> dict[str, object]:
    passed = bool(status.get("approved"))
    return {
        "name": name,
        "required": required,
        "passed": passed,
        "blocking": required and not passed,
        "invalid_reasons": list(status.get("invalid_reasons", [])),
        "next_required_action": str(status.get("next_required_action", "") or ""),
        "status": status,
    }


def policy_check_payload(
    *,
    stage: str,
    slug: str,
    spec_path: Path,
    plan_path: Path,
    state: dict[str, object],
    rel: Callable[[Path], str],
) -> dict[str, object]:
    normalized_stage = normalize_stage(stage)
    requirements = set(_STAGE_REQUIREMENTS[normalized_stage])
    spec_status = spec_approval_status_payload(spec_path=spec_path, slug=slug, state=state, rel=rel)
    plan_status = plan_approval_status_payload(
        slug=slug,
        spec_path=spec_path,
        plan_path=plan_path,
        state=state,
        rel=rel,
    )
    checks = [
        _check_payload(name="spec_approval", required="spec_approval" in requirements, status=spec_status),
        _check_payload(name="plan_approval", required="plan_approval" in requirements, status=plan_status),
    ]
    blocking_checks = [check for check in checks if bool(check["blocking"])]
    blocked_reasons: list[str] = []
    next_required_actions: list[str] = []
    for check in blocking_checks:
        name = str(check["name"])
        for reason in check["invalid_reasons"]:
            blocked_reasons.append(f"{name}:{reason}")
        action = str(check["next_required_action"]).strip()
        if action and action not in next_required_actions:
            next_required_actions.append(action)
    return {
        "feature": slug,
        "spec_path": rel(spec_path),
        "plan_path": rel(plan_path),
        "stage": normalized_stage,
        "allowed": not blocking_checks,
        "checks": checks,
        "blocked_reasons": blocked_reasons,
        "next_required_actions": next_required_actions,
    }


def command_policy_check(
    args,
    *,
    resolve_spec: Callable[[str], Path],
    spec_slug: Callable[[Path], str],
    plan_root: Path,
    read_state: Callable[[str], dict[str, object]],
    rel: Callable[[Path], str],
    json_dumps: Callable[[object], str],
) -> int:
    spec_path = resolve_spec(args.spec)
    slug = spec_slug(spec_path)
    payload = policy_check_payload(
        stage=str(args.stage),
        slug=slug,
        spec_path=spec_path,
        plan_path=plan_root / f"{slug}.json",
        state=read_state(slug),
        rel=rel,
    )
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
    else:
        status = "allowed" if payload["allowed"] else "blocked"
        print(f"Policy {payload['stage']}: {status}")
        if payload["blocked_reasons"]:
            print("Blocked reasons:")
            for reason in payload["blocked_reasons"]:
                print(f"- {reason}")
        if payload["next_required_actions"]:
            print("Next required actions:")
            for action in payload["next_required_actions"]:
                print(f"- {action}")
    return 0 if bool(payload["allowed"]) else 2
