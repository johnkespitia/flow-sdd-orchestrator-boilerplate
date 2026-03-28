"""Ola A (T01–T04): política de aprobación, comandos cortos, eventos GitHub/Jira, hidratación."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gateway.app.approval_policy import WEBHOOK_ALLOWED_INTENTS, validate_api_intent_for_policy
from gateway.app.flow_command import build_flow_command
from gateway.app.intents import (
    extract_github_acceptance_from_body,
    intent_from_github,
    intent_from_jira,
    parse_simple_approval_comment,
)
from gateway.app.models import IntentRequest


def test_t01_webhook_allowed_intents_includes_approve_review() -> None:
    assert "spec.approve" in WEBHOOK_ALLOWED_INTENTS
    assert "spec.review" in WEBHOOK_ALLOWED_INTENTS


def test_t01_api_policy_requires_approver_when_enforced() -> None:
    req = IntentRequest(source="api", intent="spec.approve", payload={"slug": "my-spec"})
    ok, code, _ = validate_api_intent_for_policy(req, enforce_approver=True)
    assert ok is False
    assert code == "APPROVER_REQUIRED"
    req2 = IntentRequest(source="api", intent="spec.approve", payload={"slug": "my-spec", "approver": "alice"})
    assert validate_api_intent_for_policy(req2, enforce_approver=True)[0] is True


def test_t02_github_simple_approve_and_review() -> None:
    reply = {"kind": "github", "provider": "github-comment"}
    a = parse_simple_approval_comment("approve my-feature-slug", source="github", reply_to=reply)
    assert a is not None and a.intent == "spec.approve" and a.payload.get("slug") == "my-feature-slug"
    b = parse_simple_approval_comment("/approve other-spec", source="github", reply_to=reply)
    assert b is not None and b.payload.get("slug") == "other-spec"
    r = parse_simple_approval_comment("review some-spec", source="github", reply_to=reply)
    assert r is not None and r.intent == "spec.review"


def test_t02_jira_comment_approve() -> None:
    payload = {
        "comment": {"body": "approve jira-approved-slug"},
        "issue": {"key": "X-1", "fields": {"summary": "t", "labels": ["flow-repo:root"]}},
    }
    out = intent_from_jira(payload)
    assert out is not None
    assert out.intent == "spec.approve"
    assert out.payload.get("slug") == "jira-approved-slug"


def test_t03_github_issues_opened_and_labeled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "specs" / "features").mkdir(parents=True)
    issue = {
        "number": 42,
        "title": "Hello",
        "body": "Desc",
        "comments_url": "https://api.github.com/repos/o/r/issues/42/comments",
        "labels": [{"name": "flow-spec"}, {"name": "flow-repo:root"}],
    }
    payload = {"action": "opened", "issue": issue, "repository": {"full_name": "o/r"}}
    req = intent_from_github("issues", payload)
    assert req is not None
    assert req.intent == "workflow.intake"
    assert "42" in req.payload.get("slug", "")

    labeled = {**payload, "action": "labeled", "label": {"name": "flow-spec"}}
    req2 = intent_from_github("issues", labeled)
    assert req2 is not None and req2.intent == "workflow.intake"


def test_t03_issue_comment_flow_and_shortcut() -> None:
    base = {
        "repository": {"full_name": "o/r"},
        "issue": {
            "number": 7,
            "title": "T",
            "body": "x",
            "comments_url": "https://api.github.com/repos/o/r/issues/7/comments",
            "labels": [{"name": "flow-repo:root"}],
            "comments": 3,
        },
        "comment": {"id": 1, "body": "/flow spec review my-slug --json"},
    }
    # /flow delegates to parse_text_command — review intent
    r = intent_from_github("issue_comment", base)
    assert r is not None and r.intent == "spec.review"

    approve_comment = {
        **base,
        "comment": {"id": 2, "body": "approve direct-approve"},
    }
    r2 = intent_from_github("issue_comment", approve_comment)
    assert r2 is not None and r2.intent == "spec.approve" and r2.payload.get("slug") == "direct-approve"


def test_t04_hydration_build_flow_command_and_github_body() -> None:
    root = Path(__file__).resolve().parents[2]
    payload = {
        "slug": "hydrate-me",
        "title": "T",
        "repos": ["root"],
        "description": "Line one",
        "acceptance_criteria": ["c1", "c2"],
    }
    cmd = build_flow_command("workflow.intake", payload, workspace_root=root)
    assert "--description" in cmd
    assert "Line one" in cmd
    assert "--acceptance-criteria" in cmd
    assert "c1" in cmd and "c2" in cmd

    body = """Intro

## Acceptance criteria
- A uno
- A dos
"""
    lines = extract_github_acceptance_from_body(body)
    assert "A uno" in lines and "A dos" in lines


def test_t04_jira_fields_acceptance_criteria(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOFTOS_JIRA_ACCEPTANCE_FIELD", raising=False)
    payload = {
        "issue": {
            "key": "P-1",
            "fields": {
                "summary": "S",
                "labels": ["flow-repo:root"],
                "description": "Plain text",
                "acceptance_criteria": ["must work"],
            },
        }
    }
    req = intent_from_jira(payload)
    assert req is not None
    assert req.payload.get("acceptance_criteria") == ["must work"]
    assert "Plain text" in (req.payload.get("description") or "")

    monkeypatch.setenv("SOFTOS_JIRA_ACCEPTANCE_FIELD", "customfield_10001")
    payload2 = {
        "issue": {
            "key": "P-2",
            "fields": {
                "summary": "S2",
                "labels": ["flow-repo:root"],
                "description": "d",
                "acceptance_criteria": ["base"],
                "customfield_10001": "- extra line\n",
            },
        }
    }
    req2 = intent_from_jira(payload2)
    assert req2 is not None
    ac = req2.payload.get("acceptance_criteria") or []
    assert "base" in ac and "extra line" in ac


def test_t03_dedupe_same_payload_same_semantic_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Dedupe en TaskStore: mismo payload/intent/source dentro de ventana -> mismo task_id."""
    monkeypatch.chdir(tmp_path)
    db = tmp_path / "t.db"
    from gateway.app.store import TaskStore

    store = TaskStore(db)
    store.initialize()
    p = {"slug": "x", "title": "x", "repos": ["root"], "description": "d"}
    a = store.enqueue(source="github", intent="workflow.intake", payload=p, command=["echo"], response_target=None)
    b = store.enqueue(source="github", intent="workflow.intake", payload=p, command=["echo"], response_target=None)
    assert a["task_id"] == b["task_id"]


def test_t01_enforce_approver_api_v1_intents(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOFTOS_GATEWAY_API_TOKEN", "tok")
    from dataclasses import replace

    from gateway.app.config import load_settings
    from gateway.app.main import app

    with TestClient(app) as client:
        base = load_settings()
        client.app.state.settings = replace(base, gateway_api_token="tok", enforce_approver_on_spec_approve_api=True)
        r = client.post(
            "/v1/intents",
            json={"source": "api", "intent": "spec.approve", "payload": {"slug": "s"}},
            headers={"authorization": "Bearer tok"},
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "APPROVER_REQUIRED"

        r2 = client.post(
            "/v1/intents",
            json={"source": "api", "intent": "spec.approve", "payload": {"slug": "s", "approver": "bob"}},
            headers={"authorization": "Bearer tok"},
        )
        assert r2.status_code == 202
