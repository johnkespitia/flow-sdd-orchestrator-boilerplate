from __future__ import annotations

import json
from pathlib import Path

from gateway.app.config import load_settings


def test_load_settings_prefers_workspace_secrets_and_db_url(monkeypatch, tmp_path: Path) -> None:  # type: ignore[override]
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    secrets_file = workspace / "workspace.secrets.json"
    secrets_file.write_text(
        json.dumps(
            {
                "SOFTOS_GATEWAY_API_TOKEN": "central-token",
                "SOFTOS_SLACK_SIGNING_SECRET": "central-slack",
                "SOFTOS_GITHUB_WEBHOOK_SECRET": "central-github",
                "SOFTOS_JIRA_WEBHOOK_TOKEN": "central-jira",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("FLOW_WORKSPACE_ROOT", str(workspace))
    monkeypatch.setenv("SOFTOS_GATEWAY_DB", str(workspace / "gateway" / "data" / "tasks.db"))
    monkeypatch.setenv("SOFTOS_GATEWAY_DB_URL", "postgresql://user:pass@localhost:5432/softos")
    monkeypatch.setenv("SOFTOS_GATEWAY_API_TOKEN", "env-token")
    monkeypatch.setenv("SOFTOS_SLACK_SIGNING_SECRET", "env-slack")
    monkeypatch.setenv("SOFTOS_GITHUB_WEBHOOK_SECRET", "env-github")
    monkeypatch.setenv("SOFTOS_JIRA_WEBHOOK_TOKEN", "env-jira")

    settings = load_settings()

    assert settings.workspace_root == workspace.resolve()
    assert settings.database_path == (workspace / "gateway" / "data" / "tasks.db").resolve()
    assert settings.database_url == "postgresql://user:pass@localhost:5432/softos"
    assert settings.gateway_api_token == "central-token"
    assert settings.slack_signing_secret == "central-slack"
    assert settings.github_webhook_secret == "central-github"
    assert settings.jira_webhook_token == "central-jira"
