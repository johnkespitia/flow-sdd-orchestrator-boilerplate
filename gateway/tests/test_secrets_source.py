from __future__ import annotations

import json
from pathlib import Path

from gateway.app.secrets_source import build_secret_source


def test_build_secret_source_prefers_workspace_secret_file_over_env(monkeypatch, tmp_path: Path) -> None:  # type: ignore[override]
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    secrets_file = workspace / "workspace.secrets.json"
    secrets_file.write_text(json.dumps({"SOFTOS_GATEWAY_API_TOKEN": "from-file"}), encoding="utf-8")

    monkeypatch.setenv("SOFTOS_GATEWAY_API_TOKEN", "from-env")
    monkeypatch.delenv("SOFTOS_GATEWAY_SECRETS_FILE", raising=False)

    source = build_secret_source(workspace_root=workspace)
    assert source.get("SOFTOS_GATEWAY_API_TOKEN") == "from-file"


def test_build_secret_source_supports_explicit_secrets_file(monkeypatch, tmp_path: Path) -> None:  # type: ignore[override]
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    explicit_file = tmp_path / "central-secrets.json"
    explicit_file.write_text(json.dumps({"SOFTOS_GITHUB_WEBHOOK_SECRET": "central-secret"}), encoding="utf-8")

    monkeypatch.setenv("SOFTOS_GATEWAY_SECRETS_FILE", str(explicit_file))

    source = build_secret_source(workspace_root=workspace)
    assert source.get("SOFTOS_GITHUB_WEBHOOK_SECRET") == "central-secret"


def test_build_secret_source_uses_legacy_gateway_file_when_central_missing(monkeypatch, tmp_path: Path) -> None:  # type: ignore[override]
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    legacy_dir = workspace / "gateway" / "data"
    legacy_dir.mkdir(parents=True)
    legacy_file = legacy_dir / "secrets.json"
    legacy_file.write_text(json.dumps({"SOFTOS_JIRA_WEBHOOK_TOKEN": "legacy-token"}), encoding="utf-8")

    monkeypatch.delenv("SOFTOS_GATEWAY_SECRETS_FILE", raising=False)

    source = build_secret_source(workspace_root=workspace)
    assert source.get("SOFTOS_JIRA_WEBHOOK_TOKEN") == "legacy-token"


def test_build_secret_source_falls_back_to_env_when_no_files_exist(monkeypatch, tmp_path: Path) -> None:  # type: ignore[override]
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)

    monkeypatch.delenv("SOFTOS_GATEWAY_SECRETS_FILE", raising=False)
    monkeypatch.setenv("SOFTOS_JIRA_WEBHOOK_TOKEN", "env-token")

    source = build_secret_source(workspace_root=workspace)
    assert source.get("SOFTOS_JIRA_WEBHOOK_TOKEN") == "env-token"
