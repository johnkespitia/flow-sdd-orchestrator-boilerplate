from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from gateway.app.main import app


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_rate_limit_exceeded_then_recovers(monkeypatch) -> None:  # type: ignore[override]
    monkeypatch.setenv("SOFTOS_GATEWAY_RATE_LIMIT_WINDOW_SECONDS", "1")
    monkeypatch.setenv("SOFTOS_GATEWAY_RATE_LIMIT_MAX_REQUESTS", "1")
    payload = _load("github_issue_opened_v1.json")
    suffix = int(time.time() * 1000)
    payload["issue"]["number"] = suffix
    payload["issue"]["title"] = f"{payload['issue']['title']} {suffix}"
    with TestClient(app) as client:
        r1 = client.post("/webhooks/github", headers={"x-github-event": "issues"}, json=payload)
        r2 = client.post("/webhooks/github", headers={"x-github-event": "issues"}, json=payload)
        assert r1.status_code == 202
        assert r2.status_code == 429
        assert r2.json()["detail"]["code"] == "RATE_LIMIT_EXCEEDED"
        time.sleep(1.1)
        r3 = client.post("/webhooks/github", headers={"x-github-event": "issues"}, json=payload)
        assert r3.status_code in {200, 202}


def test_api_auth_rejected_and_accepted(monkeypatch) -> None:  # type: ignore[override]
    monkeypatch.setenv("SOFTOS_GATEWAY_API_TOKEN", "top-secret-token")
    with TestClient(app) as client:
        rejected = client.get("/v1/repos")
        assert rejected.status_code == 401
        accepted = client.get("/v1/repos", headers={"authorization": "Bearer top-secret-token"})
        assert accepted.status_code == 200

