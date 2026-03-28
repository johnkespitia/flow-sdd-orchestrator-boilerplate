"""Política mínima de aprobación (CLI vs gateway). Ver docs/approval-policy-cli-vs-gateway.md."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import IntentRequest


# Intents permitidos vía webhooks (además de workflow.intake).
WEBHOOK_ALLOWED_INTENTS = frozenset({"workflow.intake", "spec.approve", "spec.review"})


def api_spec_approve_requires_approver(intent: str, payload: dict[str, object], *, enforce: bool) -> tuple[bool, str | None]:
    """Si enforce=True, spec.approve vía API debe incluir `approver` no vacío en payload."""
    if not enforce or intent != "spec.approve":
        return True, None
    approver = str(payload.get("approver", "")).strip()
    if approver:
        return True, None
    return False, "APPROVER_REQUIRED"


def validate_api_intent_for_policy(intent_request: "IntentRequest", *, enforce_approver: bool) -> tuple[bool, str | None, str | None]:
    """
    Valida intent entrante por /v1/intents.
    Retorna (ok, reason_code, message).
    """
    ok, code = api_spec_approve_requires_approver(intent_request.intent, intent_request.payload, enforce=enforce_approver)
    if ok:
        return True, None, None
    return False, code or "POLICY_VIOLATION", "spec.approve requiere `approver` cuando SOFTOS_GATEWAY_ENFORCE_APPROVER_ON_SPEC_APPROVE=1."
