from __future__ import annotations

import json
from pathlib import Path
import time

from fastapi.testclient import TestClient
import pytest

try:
    from gateway.app.main import app
except Exception:  # pragma: no cover - runtime compatibility guard
    app = None


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_webhook_fixtures_github_dedupe_and_rate_limit(monkeypatch) -> None:  # type: ignore[override]
    if app is None:
        pytest.skip("gateway.app.main no es importable en este runtime")
    # limit bajo para validar 429 en tercera llamada
    monkeypatch.setenv("SOFTOS_GATEWAY_RATE_LIMIT_MODE", "memory")
    monkeypatch.setenv("SOFTOS_GATEWAY_RATE_LIMIT_WINDOW_SECONDS", "60")
    monkeypatch.setenv("SOFTOS_GATEWAY_RATE_LIMIT_MAX_REQUESTS", "2")

    payload = _load("github_issue_opened_v1.json")
    # Make fixture run-unique to avoid "intake already exists" collisions.
    suffix = int(time.time() * 1000)
    payload["issue"]["number"] = suffix
    payload["issue"]["title"] = f"{payload['issue']['title']} {suffix}"
    with TestClient(app) as client:
        r1 = client.post("/webhooks/github", headers={"x-github-event": "issues"}, json=payload)
        r2 = client.post("/webhooks/github", headers={"x-github-event": "issues"}, json=payload)
        r3 = client.post("/webhooks/github", headers={"x-github-event": "issues"}, json=payload)
        assert r1.status_code == 202
        assert r2.status_code == 202
        # dedupe => mismo task_id en segunda llamada
        assert r1.json().get("task_id") == r2.json().get("task_id")
        assert r3.status_code == 429
        assert r3.json()["detail"]["code"] == "RATE_LIMIT_EXCEEDED"


def test_webhook_fixtures_jira_invalid_schema(monkeypatch) -> None:  # type: ignore[override]
    if app is None:
        pytest.skip("gateway.app.main no es importable en este runtime")
    monkeypatch.setenv("SOFTOS_GATEWAY_RATE_LIMIT_WINDOW_SECONDS", "60")
    monkeypatch.setenv("SOFTOS_GATEWAY_RATE_LIMIT_MAX_REQUESTS", "100")
    with TestClient(app) as client:
        response = client.post("/webhooks/jira", json={"issue": {"fields": {}}})
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "MISSING_SUMMARY"


def test_webhook_fixtures_slack_validation(monkeypatch) -> None:  # type: ignore[override]
    if app is None:
        pytest.skip("gateway.app.main no es importable en este runtime")
    monkeypatch.setenv("SOFTOS_GATEWAY_RATE_LIMIT_WINDOW_SECONDS", "60")
    monkeypatch.setenv("SOFTOS_GATEWAY_RATE_LIMIT_MAX_REQUESTS", "100")
    payload = _load("slack_command_v1.json")
    with TestClient(app) as client:
        response = client.post("/webhooks/slack/commands", data=payload)
        assert response.status_code == 200
        assert "Aceptado task" in response.text
