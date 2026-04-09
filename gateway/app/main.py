from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from hashlib import sha256
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from .config import Settings, load_settings
from .feedback import send_feedback_event
from .flow_command import build_flow_command
from .gateway_config import load_gateway_block
from .intents import IntentError, intent_from_github, intent_from_jira, parse_text_command, slugify
from .spec_quality import lint_inbound_spec_payload
from .transforms import apply_source_transforms
from .models import (
    IntentRequest,
    RepoCatalogView,
    TaskCommentRequest,
    SpecClaimRequest,
    SpecHeartbeatRequest,
    SpecReassignRequest,
    SpecReleaseRequest,
    SpecSourceView,
    SpecTransitionRequest,
    SpecView,
    TaskAccepted,
    TaskView,
)
from .repos import repo_catalog_payload
from .security import verify_bearer_token, verify_github_signature, verify_slack_signature
from .store import SpecRegistryError, TaskStore
from .worker import TaskWorker
from flowctl.operations import collect_workflow_metrics
from .approval_policy import WEBHOOK_ALLOWED_INTENTS, validate_api_intent_for_policy
from .auth import require_api_auth
from .webhook_validation import validate_github_payload, validate_jira_payload, validate_slack_command
from .rate_limit import SlidingWindowRateLimiter


def _accepted_payload(task: dict[str, Any]) -> TaskAccepted:
    return TaskAccepted(
        task_id=task["task_id"],
        status=task["status"],
        intent=task["intent"],
        source=task["source"],
    )


def _view_payload(task: dict[str, Any]) -> TaskView:
    return TaskView(**task)


def _spec_payload(spec: dict[str, Any]) -> SpecView:
    return SpecView(**spec)


def _spec_source_payload(*, spec_id: str, path: Path, content: str) -> SpecSourceView:
    updated_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat()
    return SpecSourceView(
        spec_id=spec_id,
        path=str(path),
        content=content,
        updated_at=updated_at,
        content_sha256=sha256(content.encode("utf-8")).hexdigest(),
    )


def _intake_spec_exists(settings: Settings, intent_request: IntentRequest) -> tuple[bool, str]:
    if intent_request.intent != "workflow.intake":
        return False, ""
    slug = slugify(str(intent_request.payload.get("slug", "")))
    if not slug:
        return False, ""
    spec_path = settings.workspace_root / "specs" / "features" / f"{slug}.spec.md"
    return spec_path.is_file(), slug


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    store = TaskStore(settings.database_path, database_url=settings.database_url)
    store.initialize()
    store.reset_running_tasks()
    worker = TaskWorker(settings, store)
    worker.start()
    app.state.settings = settings
    app.state.store = store
    app.state.worker = worker
    rate_limit_mode = str(os.getenv("SOFTOS_GATEWAY_RATE_LIMIT_MODE", "db") or "db").strip().lower()
    app.state.rate_limit_mode = rate_limit_mode
    app.state.rate_limit_window_seconds = max(
        1, int(os.getenv("SOFTOS_GATEWAY_RATE_LIMIT_WINDOW_SECONDS", "60") or "60")
    )
    app.state.rate_limit_max_requests = max(
        1, int(os.getenv("SOFTOS_GATEWAY_RATE_LIMIT_MAX_REQUESTS", "30") or "30")
    )
    if rate_limit_mode == "memory":
        app.state.rate_limiter = SlidingWindowRateLimiter(
            window_seconds=app.state.rate_limit_window_seconds,
            max_requests=app.state.rate_limit_max_requests,
        )
    else:
        app.state.rate_limiter = None
    yield
    worker.stop()


app = FastAPI(title="SoftOS Gateway", version="0.1.0", lifespan=lifespan)


def enqueue_intent(app_request: Request, intent_request: IntentRequest) -> dict[str, Any]:
    settings: Settings = app_request.app.state.settings
    ok, code, msg = validate_api_intent_for_policy(
        intent_request,
        enforce_approver=bool(getattr(settings, "enforce_approver_on_spec_approve_api", False)),
    )
    if not ok:
        raise HTTPException(status_code=400, detail={"code": code or "POLICY_VIOLATION", "message": msg or "Policy rejected intent."})

    store: TaskStore = app_request.app.state.store
    payload = apply_source_transforms(intent_request.source, dict(intent_request.payload), settings.workspace_root)
    if intent_request.intent == "workflow.intake":
        issues = lint_inbound_spec_payload(payload)
        gw = load_gateway_block(settings.workspace_root)
        lint_cfg = gw.get("spec_inbound_lint", {}) if isinstance(gw, dict) else {}
        if issues:
            payload = {**payload, "_lint_findings": issues}
        if issues and bool(lint_cfg.get("reject_on_error")):
            raise HTTPException(
                status_code=400,
                detail={"code": "SPEC_INBOUND_LINT", "message": "; ".join(issues[:12])},
            )
    command = build_flow_command(
        intent_request.intent,
        payload,
        workspace_root=settings.workspace_root,
    )
    return store.enqueue(
        source=intent_request.source,
        intent=intent_request.intent,
        payload=payload,
        command=command,
        response_target=intent_request.reply_to,
    )


def _require_allowed_webhook_intent(intent_request: IntentRequest, *, source: str, store: TaskStore, raw_payload: dict[str, Any]) -> None:
    if intent_request.intent in WEBHOOK_ALLOWED_INTENTS:
        return
    reason = (
        f"Webhook intent not allowed: `{intent_request.intent}`. "
        f"Permitidos: {', '.join(sorted(WEBHOOK_ALLOWED_INTENTS))}."
    )
    store.record_intake_failure(source=source, reason=reason, payload=raw_payload)
    raise HTTPException(status_code=400, detail={"code": "WEBHOOK_INTENT_NOT_ALLOWED", "message": reason})


def _enforce_rate_limit(request: Request, *, source: str, endpoint: str) -> None:
    store: TaskStore = request.app.state.store
    mode = str(getattr(request.app.state, "rate_limit_mode", "db") or "db").strip().lower()
    actor = str(request.headers.get("x-api-actor") or "").strip()
    forwarded_for = str(request.headers.get("x-forwarded-for") or "").strip()
    client_host = (request.client.host if request.client else "") or ""
    actor_or_ip = actor or (forwarded_for.split(",")[0].strip() if forwarded_for else "") or client_host or "anonymous"
    allowed = True
    if mode == "memory":
        limiter: SlidingWindowRateLimiter = request.app.state.rate_limiter
        key = f"{source}:{endpoint}:{actor_or_ip}"
        allowed = limiter.allow(key)
    else:
        result = store.check_rate_limit(
            source=source,
            endpoint=endpoint,
            actor_key=actor_or_ip,
            window_seconds=int(getattr(request.app.state, "rate_limit_window_seconds", 60)),
            max_requests=int(getattr(request.app.state, "rate_limit_max_requests", 30)),
        )
        allowed = bool(result.get("allowed", False))
    if allowed:
        return

    store.record_intake_failure(source=source, reason="RATE_LIMIT_EXCEEDED", payload={"endpoint": endpoint})
    store.record_auth_audit(
        actor=actor_or_ip,
        source=source,
        endpoint=endpoint,
        decision="rejected",
        reason_code="RATE_LIMIT_EXCEEDED",
        correlation_id=str(request.headers.get("x-request-id") or "").strip() or None,
    )
    raise HTTPException(
        status_code=429,
        detail={"code": "RATE_LIMIT_EXCEEDED", "message": "Too many requests for this source/endpoint."},
    )


@app.get("/healthz")
async def healthz(request: Request) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    return {
        "status": "ok",
        "workspace_root": str(settings.workspace_root),
        "database_path": str(settings.database_path),
    }


@app.get("/metrics")
async def metrics(request: Request) -> JSONResponse:
    settings: Settings = request.app.state.settings
    store: TaskStore = request.app.state.store
    payload = collect_workflow_metrics(root=settings.workspace_root, utc_now=lambda: datetime.now(timezone.utc).isoformat())
    payload = dict(payload)
    payload["gateway_intent_metrics"] = store.aggregate_intent_provider_metrics()
    return JSONResponse(payload)


@app.get("/v1/ops/monitor", response_class=HTMLResponse)
async def ops_monitor(request: Request) -> HTMLResponse:
    """T15: vista mínima de tareas recientes (HTML)."""
    _ = require_api_auth(request, endpoint="/v1/ops/monitor", source="api")
    store: TaskStore = request.app.state.store
    rows = store.recent_tasks(limit=40)
    trs = []
    for t in rows:
        trs.append(
            "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                t.get("task_id", ""),
                t.get("source", ""),
                t.get("intent", ""),
                t.get("status", ""),
                t.get("created_at", ""),
                t.get("finished_at") or "",
            )
        )
    body = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Gateway task monitor</title>"
        "<style>body{font-family:system-ui;margin:16px;} table{border-collapse:collapse;} td,th{border:1px solid #ccc;padding:4px 8px;font-size:13px;}</style></head><body>"
        "<h2>SoftOS Gateway — task monitor</h2><table><thead><tr>"
        "<th>task_id</th><th>source</th><th>intent</th><th>status</th><th>created</th><th>finished</th></tr></thead><tbody>"
        + "".join(trs)
        + "</tbody></table></body></html>"
    )
    return HTMLResponse(body)


@app.post("/v1/intents", response_model=TaskAccepted, status_code=202)
async def create_intent(intent_request: IntentRequest, request: Request) -> TaskAccepted:
    _ = require_api_auth(request, endpoint="/v1/intents", source=str(intent_request.source or "api"))
    try:
        task = enqueue_intent(request, intent_request)
    except IntentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _accepted_payload(task)


@app.get("/v1/repos", response_model=RepoCatalogView)
async def list_repos(request: Request) -> RepoCatalogView:
    settings: Settings = request.app.state.settings
    _ = require_api_auth(request, endpoint="/v1/repos", source="api")
    return RepoCatalogView(**repo_catalog_payload(settings.workspace_root))


@app.get("/v1/tasks/{task_id}", response_model=TaskView)
async def get_task(task_id: str, request: Request) -> TaskView:
    _ = require_api_auth(request, endpoint="/v1/tasks/{task_id}", source="api")
    store: TaskStore = request.app.state.store
    try:
        task = store.get(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found.") from exc
    return _view_payload(task)


@app.post("/v1/tasks/{task_id}/comments", response_model=TaskView)
async def add_task_comment(task_id: str, payload: TaskCommentRequest, request: Request) -> TaskView:
    _ = require_api_auth(request, endpoint="/v1/tasks/{task_id}/comments", source=str(payload.source or "api"))
    store: TaskStore = request.app.state.store
    try:
        task = store.append_comment(
            task_id=task_id,
            actor=payload.actor,
            message=payload.message,
            source=payload.source,
            direction=payload.direction,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found.") from exc
    try:
        send_feedback_event(
            request.app.state.settings,
            event="comment_added",
            source=str(payload.source or "api"),
            status=str(task.get("status") or "accepted"),
            payload={
                "task_id": task_id,
                "actor": payload.actor,
                "direction": payload.direction,
                "message": payload.message,
            },
            response_target=task.get("response_target") if isinstance(task.get("response_target"), dict) else None,
        )
    except Exception:
        pass
    return _view_payload(task)


@app.post("/webhooks/slack/commands")
async def slack_commands(request: Request) -> PlainTextResponse:
    _enforce_rate_limit(request, source="slack", endpoint="/webhooks/slack/commands")
    settings: Settings = request.app.state.settings
    body = await request.body()
    if not verify_slack_signature(
        signing_secret=settings.slack_signing_secret,
        timestamp=request.headers.get("x-slack-request-timestamp"),
        signature=request.headers.get("x-slack-signature"),
        body=body,
    ):
        raise HTTPException(status_code=401, detail="Invalid Slack signature.")

    form = await request.form()
    ok, code, message = validate_slack_command(dict(form))
    if not ok:
        request.app.state.store.record_intake_failure(source="slack", reason=f"{code}:{message}", payload={"code": code})
        raise HTTPException(status_code=400, detail={"code": code, "message": message})
    if str(form.get("ssl_check", "")).strip() == "1":
        return PlainTextResponse("")
    text = str(form.get("text", "")).strip()
    response_url = str(form.get("response_url", "")).strip()
    try:
        intent_request = parse_text_command(
            text,
            source="slack",
            reply_to={
                "kind": "slack",
                "provider": "slack-webhook",
                "response_url": response_url,
                "channel_id": str(form.get("channel_id", "")).strip(),
            },
        )
        _require_allowed_webhook_intent(intent_request, source="slack", store=request.app.state.store, raw_payload={"text": text})
        task = enqueue_intent(request, intent_request)
    except IntentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return PlainTextResponse(f"Aceptado task {task['task_id']} para `{task['intent']}`.")


@app.post("/webhooks/github")
async def github_webhook(request: Request) -> JSONResponse:
    _enforce_rate_limit(request, source="github", endpoint="/webhooks/github")
    settings: Settings = request.app.state.settings
    body = await request.body()
    if not verify_github_signature(
        secret=settings.github_webhook_secret,
        signature=request.headers.get("x-hub-signature-256"),
        body=body,
    ):
        raise HTTPException(status_code=401, detail="Invalid GitHub signature.")

    event = request.headers.get("x-github-event", "")
    payload = await request.json()
    ok, code, message = validate_github_payload(event, payload)
    if not ok:
        request.app.state.store.record_intake_failure(source="github", reason=f"{code}:{message}", payload={"code": code, "event": event})
        raise HTTPException(status_code=400, detail={"code": code, "message": message})
    try:
        intent_request = intent_from_github(event, payload)
    except IntentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if intent_request is None:
        request.app.state.store.record_intake_failure(
            source="github",
            reason="No workflow.intake mapping for event.",
            payload={"event": event},
        )
        return JSONResponse({"accepted": False, "reason": "event ignored"}, status_code=200)
    _require_allowed_webhook_intent(intent_request, source="github", store=request.app.state.store, raw_payload=payload)
    if intent_request.intent != "workflow.intake":
        try:
            task = enqueue_intent(request, intent_request)
        except IntentError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(_accepted_payload(task).model_dump(), status_code=202)

    exists, slug = _intake_spec_exists(settings, intent_request)
    if exists:
        request.app.state.store.record_intake_failure(
            source="github",
            reason=f"Intake already exists for slug `{slug}`.",
            payload={"event": event, "slug": slug},
        )
        return JSONResponse(
            {"accepted": False, "reason": "intake already exists", "slug": slug},
            status_code=200,
        )

    try:
        task = enqueue_intent(request, intent_request)
    except IntentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(_accepted_payload(task).model_dump(), status_code=202)


@app.post("/webhooks/jira")
async def jira_webhook(request: Request) -> JSONResponse:
    _enforce_rate_limit(request, source="jira", endpoint="/webhooks/jira")
    settings: Settings = request.app.state.settings
    auth_header = request.headers.get("authorization") or request.headers.get("x-jira-token")
    if settings.jira_webhook_token and not verify_bearer_token(auth_header, settings.jira_webhook_token):
        raise HTTPException(status_code=401, detail="Invalid Jira token.")

    payload = await request.json()
    ok, code, message = validate_jira_payload(payload)
    if not ok:
        request.app.state.store.record_intake_failure(source="jira", reason=f"{code}:{message}", payload={"code": code})
        raise HTTPException(status_code=400, detail={"code": code, "message": message})
    try:
        intent_request = intent_from_jira(payload)
    except IntentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if intent_request is None:
        request.app.state.store.record_intake_failure(
            source="jira",
            reason="No workflow.intake mapping for event.",
            payload=payload if isinstance(payload, dict) else {},
        )
        return JSONResponse({"accepted": False, "reason": "event ignored"}, status_code=200)
    _require_allowed_webhook_intent(intent_request, source="jira", store=request.app.state.store, raw_payload=payload)

    if intent_request.intent != "workflow.intake":
        try:
            task = enqueue_intent(request, intent_request)
        except IntentError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(_accepted_payload(task).model_dump(), status_code=202)

    try:
        task = enqueue_intent(request, intent_request)
    except IntentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(_accepted_payload(task).model_dump(), status_code=202)


def _sanitize_spec_id(spec_id: str) -> str:
    normalized = spec_id.strip().lower()
    if not normalized:
        raise HTTPException(status_code=400, detail={"code": "INVALID_SPEC_ID", "message": "Invalid spec id."})
    return normalized


def _resolve_spec_source_path(settings: Settings, spec_id: str) -> Path:
    specs_root = settings.workspace_root / "specs"
    preferred = specs_root / "features" / f"{spec_id}.spec.md"
    if preferred.is_file():
        return preferred
    candidates = sorted(specs_root.rglob(f"{spec_id}.spec.md"))
    if not candidates:
        raise HTTPException(
            status_code=404,
            detail={"code": "SPEC_SOURCE_NOT_FOUND", "message": "Canonical spec source not found."},
        )
    return candidates[0]


@app.post("/v1/specs/{spec_id}/claim", response_model=SpecView)
async def claim_spec(spec_id: str, payload: SpecClaimRequest, request: Request) -> SpecView:
    _ = require_api_auth(request, endpoint="/v1/specs/{spec_id}/claim", source=str(payload.source or "api"))
    store: TaskStore = request.app.state.store
    try:
        record = store.claim_spec(
            spec_id=_sanitize_spec_id(spec_id),
            actor=payload.actor,
            source=payload.source,
            reason=payload.reason,
            ttl_seconds=payload.ttl_seconds,
        )
    except SpecRegistryError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    store.append_task_event(
        task_id=None,
        event="claimed",
        source=payload.source,
        status="accepted",
        payload={"spec_id": _sanitize_spec_id(spec_id), "actor": payload.actor},
    )
    try:
        send_feedback_event(
            request.app.state.settings,
            event="claimed",
            source=payload.source,
            status="accepted",
            payload={"spec_id": _sanitize_spec_id(spec_id), "actor": payload.actor},
        )
    except Exception:
        pass
    return _spec_payload(record)


@app.post("/v1/specs/{spec_id}/heartbeat", response_model=SpecView)
async def heartbeat_spec(spec_id: str, payload: SpecHeartbeatRequest, request: Request) -> SpecView:
    _ = require_api_auth(request, endpoint="/v1/specs/{spec_id}/heartbeat", source=str(payload.source or "api"))
    store: TaskStore = request.app.state.store
    try:
        record = store.heartbeat_spec(
            spec_id=_sanitize_spec_id(spec_id),
            actor=payload.actor,
            lock_token=payload.lock_token,
            source=payload.source,
            reason=payload.reason,
            ttl_seconds=payload.ttl_seconds,
        )
    except SpecRegistryError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return _spec_payload(record)


@app.post("/v1/specs/{spec_id}/release", response_model=SpecView)
async def release_spec(spec_id: str, payload: SpecReleaseRequest, request: Request) -> SpecView:
    _ = require_api_auth(request, endpoint="/v1/specs/{spec_id}/release", source=str(payload.source or "api"))
    store: TaskStore = request.app.state.store
    try:
        record = store.release_spec(
            spec_id=_sanitize_spec_id(spec_id),
            actor=payload.actor,
            lock_token=payload.lock_token,
            source=payload.source,
            reason=payload.reason,
        )
    except SpecRegistryError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return _spec_payload(record)


@app.post("/v1/specs/{spec_id}/reassign", response_model=SpecView)
async def reassign_spec(spec_id: str, payload: SpecReassignRequest, request: Request) -> SpecView:
    _ = require_api_auth(request, endpoint="/v1/specs/{spec_id}/reassign", source=str(payload.source or "api"))
    store: TaskStore = request.app.state.store
    try:
        record = store.reassign_spec(
            spec_id=_sanitize_spec_id(spec_id),
            actor=payload.actor,
            to_actor=payload.to_actor,
            lock_token=payload.lock_token,
            source=payload.source,
            reason=payload.reason,
            ttl_seconds=payload.ttl_seconds,
        )
    except SpecRegistryError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return _spec_payload(record)


@app.post("/v1/specs/{spec_id}/transition", response_model=SpecView)
async def transition_spec(spec_id: str, payload: SpecTransitionRequest, request: Request) -> SpecView:
    _ = require_api_auth(request, endpoint="/v1/specs/{spec_id}/transition", source=str(payload.source or "api"))
    store: TaskStore = request.app.state.store
    try:
        record = store.transition_spec(
            spec_id=_sanitize_spec_id(spec_id),
            actor=payload.actor,
            to_state=payload.to_state,
            source=payload.source,
            reason=payload.reason,
            lock_token=payload.lock_token,
        )
    except SpecRegistryError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return _spec_payload(record)


@app.get("/v1/specs/{spec_id}", response_model=SpecView)
async def get_spec(spec_id: str, request: Request) -> SpecView:
    _ = require_api_auth(request, endpoint="/v1/specs/{spec_id}", source="api")
    store: TaskStore = request.app.state.store
    try:
        record = store.get_spec(_sanitize_spec_id(spec_id))
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail={"code": "SPEC_NOT_FOUND", "message": "Spec not found in registry."}
        ) from exc
    return _spec_payload(record)


@app.get("/v1/specs/{spec_id}/source", response_model=SpecSourceView)
async def get_spec_source(spec_id: str, request: Request) -> SpecSourceView:
    _ = require_api_auth(request, endpoint="/v1/specs/{spec_id}/source", source="api")
    settings: Settings = request.app.state.settings
    normalized_spec_id = _sanitize_spec_id(spec_id)
    source_path = _resolve_spec_source_path(settings, normalized_spec_id)
    content = source_path.read_text(encoding="utf-8")
    return _spec_source_payload(spec_id=normalized_spec_id, path=source_path, content=content)


@app.get("/v1/specs")
async def list_specs(request: Request, state: str | None = None, assignee: str | None = None) -> dict[str, Any]:
    _ = require_api_auth(request, endpoint="/v1/specs", source="api")
    store: TaskStore = request.app.state.store
    return {"items": store.list_specs(state=state, assignee=assignee)}
