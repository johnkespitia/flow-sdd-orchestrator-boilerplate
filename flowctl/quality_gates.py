from __future__ import annotations

from pathlib import Path

RISK_LEVELS = ("low", "medium", "high", "critical")
RISK_INDEX = {level: idx for idx, level in enumerate(RISK_LEVELS)}


def classify_slice_risk(slice_payload: dict[str, object]) -> dict[str, object]:
    targets = [str(item).lower() for item in slice_payload.get("owned_targets", []) if str(item).strip()]
    reasons: list[str] = []
    level = "low"
    for target in targets:
        if any(token in target for token in ("infra/", "terraform", "production", "security", "auth", "payment", "migrations")):
            level = "critical"
            reasons.append(f"critical-target:{target}")
            break
    if level != "critical":
        if any(token in target for token in ("/api/", "dto", "contract", "schema", "release", "gateway")):
            level = "high"
            reasons.append("api-dto-or-contract-surface")
        elif len(targets) >= 6:
            level = "medium"
            reasons.append("large-write-set")
    return {"level": level, "reasons": reasons}


def detect_api_dto_change(plan_payload: dict[str, object] | None) -> bool:
    if not isinstance(plan_payload, dict):
        return False
    for slice_payload in plan_payload.get("slices", []):
        if not isinstance(slice_payload, dict):
            continue
        for target in slice_payload.get("owned_targets", []):
            normalized = str(target).lower()
            if any(token in normalized for token in ("/api/", "dto", "contract", "schema")):
                return True
    return False


def max_risk_level(plan_payload: dict[str, object] | None) -> str:
    if not isinstance(plan_payload, dict):
        return "low"
    maximum = "low"
    for slice_payload in plan_payload.get("slices", []):
        if not isinstance(slice_payload, dict):
            continue
        level = str(classify_slice_risk(slice_payload)["level"])
        if RISK_INDEX[level] > RISK_INDEX[maximum]:
            maximum = level
    return maximum


def risk_thresholds_by_level() -> dict[str, int]:
    return {"low": 50, "medium": 65, "high": 80, "critical": 90}


def required_checkpoints(stage_name: str, risk_level: str, api_dto_change: bool) -> list[str]:
    required: list[str] = []
    if stage_name == "plan":
        required = ["plan-stage-pass"]
    elif stage_name == "slice_start":
        required = ["slice_start-stage-pass"]
    elif stage_name == "ci_spec":
        required = ["ci_spec-stage-pass", "drift-check-pass"]
        if api_dto_change:
            required.extend(["generate-contracts-pass", "contract-verify-pass"])
    elif stage_name == "ci_repo":
        required = ["ci_repo-stage-pass"]
    elif stage_name == "ci_integration":
        required = ["ci_integration-stage-pass"]
        if risk_level in {"high", "critical"}:
            required.append("ci-integration-extended-pass")
    elif stage_name == "release_promote":
        required = ["confidence-threshold-pass"]
        if risk_level in {"high", "critical"}:
            required.append("additional-reviewer-pass")
    elif stage_name in {"release_verify", "infra_apply"}:
        required = [f"{stage_name}-stage-pass"]
    return required


def slice_confidence_score(
    *,
    slice_payload: dict[str, object],
    stage_records: dict[str, dict[str, object]],
    contract_ok: bool,
    drift_ok: bool,
) -> dict[str, object]:
    def _is_stage_healthy(status: str) -> bool:
        return status in {"passed", "skipped"}

    risk = classify_slice_risk(slice_payload)
    score = 0
    ci_spec = _is_stage_healthy(str(stage_records.get("ci_spec", {}).get("status")))
    ci_repo = _is_stage_healthy(str(stage_records.get("ci_repo", {}).get("status")))
    ci_integration = _is_stage_healthy(str(stage_records.get("ci_integration", {}).get("status")))
    score += 40 if ci_spec else 0
    score += 30 if ci_repo else 0
    score += 15 if ci_integration else 0

    linked_tests = [str(item).strip() for item in slice_payload.get("linked_tests", []) if str(item).strip()]
    score += min(15, len(linked_tests) * 5) if linked_tests else 3

    risk_bonus = {"low": 20, "medium": 12, "high": 6, "critical": 0}
    score += risk_bonus[str(risk["level"])]
    score += 15 if contract_ok else 0
    score += 10 if drift_ok else 0
    score = min(100, score)
    return {"slice": str(slice_payload.get("name", "")).strip(), "risk_level": risk["level"], "score": score}


def build_traceability_matrix(
    *,
    feature_slug: str,
    plan_payload: dict[str, object] | None,
    state: dict[str, object],
    stage_records: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    matrix: list[dict[str, object]] = []
    if not isinstance(plan_payload, dict):
        return matrix
    slice_results = state.get("slice_results", {})
    if not isinstance(slice_results, dict):
        slice_results = {}
    release_status = {
        "promote": str(stage_records.get("release_promote", {}).get("status") or "unknown"),
        "verify": str(stage_records.get("release_verify", {}).get("status") or "unknown"),
    }
    for slice_payload in plan_payload.get("slices", []):
        if not isinstance(slice_payload, dict):
            continue
        name = str(slice_payload.get("name", "")).strip()
        if not name:
            continue
        result = slice_results.get(name, {}) if isinstance(slice_results.get(name), dict) else {}
        matrix.append(
            {
                "spec": feature_slug,
                "slice": name,
                "commit": result.get("commit_ref"),
                "test": [str(item) for item in slice_payload.get("linked_tests", [])],
                "release": release_status,
            }
        )
    return matrix

