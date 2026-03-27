"""Asegura que el runbook de payloads canónicos (Ola 9 master plan) existe y es coherente."""
from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_webhook_canonical_payloads_doc_exists() -> None:
    root = _repo_root()
    doc = root / "docs" / "webhook-canonical-payloads.md"
    assert doc.is_file(), "docs/webhook-canonical-payloads.md debe existir"
    text = doc.read_text(encoding="utf-8")
    assert "GitHub" in text
    assert "Jira" in text
    assert "Slack" in text
    assert "/webhooks/github" in text
    assert "/webhooks/jira" in text
    assert "/webhooks/slack/commands" in text


def test_fixtures_match_doc_references() -> None:
    root = _repo_root()
    fixtures = root / "gateway" / "tests" / "fixtures"
    for name in (
        "github_issue_opened_v1.json",
        "github_issue_comment_v1.json",
        "jira_issue_created_v1.json",
        "slack_command_v1.json",
    ):
        assert (fixtures / name).is_file(), f"fixture faltante: {name}"
