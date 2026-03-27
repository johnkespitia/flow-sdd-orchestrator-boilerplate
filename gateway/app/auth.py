from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, Request

from .config import Settings
from .security import verify_bearer_token
from .store import TaskStore


def _correlation_id(request: Request) -> str:
    header = str(request.headers.get("x-request-id") or "").strip()
    return header if header else uuid.uuid4().hex


def _actor(request: Request) -> str | None:
    # Optional; used only for audit.
    value = str(request.headers.get("x-softos-actor") or "").strip()
    return value if value else None


def require_api_auth(request: Request, *, endpoint: str, source: str = "api") -> dict[str, Any]:
    """
    Enforce consistent auth for sensitive endpoints.
    - If SOFTOS_GATEWAY_API_TOKEN is configured -> require bearer token.
    - Always writes auth_audit record with decision accepted/rejected.
    """
    settings: Settings = request.app.state.settings
    store: TaskStore = request.app.state.store
    correlation_id = _correlation_id(request)
    actor = _actor(request)
    auth_header = request.headers.get("authorization")

    if not settings.gateway_api_token:
        store.record_auth_audit(
            actor=actor,
            source=source,
            endpoint=endpoint,
            decision="accepted",
            reason_code="AUTH_DISABLED",
            correlation_id=correlation_id,
        )
        return {"actor": actor, "correlation_id": correlation_id}

    if not verify_bearer_token(auth_header, settings.gateway_api_token):
        store.record_auth_audit(
            actor=actor,
            source=source,
            endpoint=endpoint,
            decision="rejected",
            reason_code="INVALID_API_TOKEN",
            correlation_id=correlation_id,
        )
        raise HTTPException(status_code=401, detail={"code": "INVALID_API_TOKEN", "message": "Invalid API token."})

    store.record_auth_audit(
        actor=actor,
        source=source,
        endpoint=endpoint,
        decision="accepted",
        reason_code="API_TOKEN_OK",
        correlation_id=correlation_id,
    )
    return {"actor": actor, "correlation_id": correlation_id}

