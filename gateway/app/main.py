from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from .config import Settings, load_settings
from .feedback import send_feedback_event
from .intents import IntentError, build_flow_command, intent_from_github, intent_from_jira, parse_text_command, slugify
from .models import (
    IntentRequest,
    RepoCatalogView,
    TaskCommentRequest,
    SpecClaimRequest,
    SpecHeartbeatRequest,
    SpecReleaseRequest,
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
    store = TaskStore(settings.database_path)
    store.initialize()
    store.reset_running_tasks()
    worker = TaskWorker(settings, store)
    worker.start()
    app.state.settings = settings
    app.state.store = store
    app.state.worker = worker
    yield
    worker.stop()


app = FastAPI(title="SoftOS Gateway", version="0.1.0", lifespan=lifespan)


def enqueue_intent(app_request: Request, intent_request: IntentRequest) -> dict[str, Any]:
    settings: Settings = app_request.app.state.settings
    store: TaskStore = app_request.app.state.store
    command = build_flow_command(
        intent_request.intent,
        intent_request.payload,
        workspace_root=settings.workspace_root,
    )
    return store.enqueue(
        source=intent_request.source,
        intent=intent_request.intent,
        payload=intent_request.payload,
        command=command,
        response_target=intent_request.reply_to,
    )


def _require_workflow_intake(intent_request: IntentRequest, *, source: str, store: TaskStore, raw_payload: dict[str, Any]) -> None:
    if intent_request.intent == "workflow.intake":
        return
    reason = f"Webhook intent not allowed: `{intent_request.intent}`. Only `workflow.intake` is accepted."
    store.record_intake_failure(source=source, reason=reason, payload=raw_payload)
    raise HTTPException(status_code=400, detail={"code": "WEBHOOK_INTENT_NOT_ALLOWED", "message": reason})


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
    payload = collect_workflow_metrics(root=settings.workspace_root, utc_now=lambda: datetime.now(timezone.utc).isoformat())
    return JSONResponse(payload)


@app.post("/v1/intents", response_model=TaskAccepted, status_code=202)
async def create_intent(intent_request: IntentRequest, request: Request) -> TaskAccepted:
    settings: Settings = request.app.state.settings
    auth_header = request.headers.get("authorization")
    if settings.gateway_api_token and not verify_bearer_token(auth_header, settings.gateway_api_token):
        raise HTTPException(status_code=401, detail="Invalid API token.")
    try:
        task = enqueue_intent(request, intent_request)
    except IntentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _accepted_payload(task)


@app.get("/v1/repos", response_model=RepoCatalogView)
async def list_repos(request: Request) -> RepoCatalogView:
    settings: Settings = request.app.state.settings
    auth_header = request.headers.get("authorization")
    if settings.gateway_api_token and not verify_bearer_token(auth_header, settings.gateway_api_token):
        raise HTTPException(status_code=401, detail="Invalid API token.")
    return RepoCatalogView(**repo_catalog_payload(settings.workspace_root))


@app.get("/v1/tasks/{task_id}", response_model=TaskView)
async def get_task(task_id: str, request: Request) -> TaskView:
    store: TaskStore = request.app.state.store
    try:
        task = store.get(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found.") from exc
    return _view_payload(task)


@app.post("/v1/tasks/{task_id}/comments", response_model=TaskView)
async def add_task_comment(task_id: str, payload: TaskCommentRequest, request: Request) -> TaskView:
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
    return _view_payload(task)


@app.post("/webhooks/slack/commands")
async def slack_commands(request: Request) -> PlainTextResponse:
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
        _require_workflow_intake(intent_request, source="slack", store=request.app.state.store, raw_payload={"text": text})
        task = enqueue_intent(request, intent_request)
    except IntentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return PlainTextResponse(f"Aceptado task {task['task_id']} para `{task['intent']}`.")


@app.post("/webhooks/github")
async def github_webhook(request: Request) -> JSONResponse:
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
    _require_workflow_intake(intent_request, source="github", store=request.app.state.store, raw_payload=payload)
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
    settings: Settings = request.app.state.settings
    auth_header = request.headers.get("authorization") or request.headers.get("x-jira-token")
    if settings.jira_webhook_token and not verify_bearer_token(auth_header, settings.jira_webhook_token):
        raise HTTPException(status_code=401, detail="Invalid Jira token.")

    payload = await request.json()
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
    _require_workflow_intake(intent_request, source="jira", store=request.app.state.store, raw_payload=payload)

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


@app.post("/v1/specs/{spec_id}/claim", response_model=SpecView)
async def claim_spec(spec_id: str, payload: SpecClaimRequest, request: Request) -> SpecView:
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


@app.post("/v1/specs/{spec_id}/transition", response_model=SpecView)
async def transition_spec(spec_id: str, payload: SpecTransitionRequest, request: Request) -> SpecView:
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
    store: TaskStore = request.app.state.store
    try:
        record = store.get_spec(_sanitize_spec_id(spec_id))
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail={"code": "SPEC_NOT_FOUND", "message": "Spec not found in registry."}
        ) from exc
    return _spec_payload(record)


@app.get("/v1/specs")
async def list_specs(request: Request, state: str | None = None, assignee: str | None = None) -> dict[str, Any]:
    store: TaskStore = request.app.state.store
    return {"items": store.list_specs(state=state, assignee=assignee)}
