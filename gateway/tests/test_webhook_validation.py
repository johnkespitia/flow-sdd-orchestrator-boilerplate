from __future__ import annotations

from gateway.app.webhook_validation import validate_github_payload, validate_jira_payload, validate_slack_command


def test_github_validation_rejects_non_object() -> None:
    ok, code, _ = validate_github_payload("issues", "not-a-dict")
    assert not ok
    assert code == "INVALID_JSON"


def test_github_validation_accepts_minimal_issue_comment() -> None:
    payload = {"repository": {"full_name": "x/y"}, "issue": {"number": 1}, "comment": {"body": "/spec hi"}}
    ok, code, _ = validate_github_payload("issue_comment", payload)
    assert ok
    assert code == ""


def test_jira_validation_requires_summary() -> None:
    ok, code, _ = validate_jira_payload({"issue": {"fields": {}}})
    assert not ok
    assert code == "MISSING_SUMMARY"


def test_slack_validation_requires_text_and_response_url() -> None:
    ok, code, _ = validate_slack_command({"text": "", "response_url": ""})
    assert not ok
    assert code in {"MISSING_TEXT", "MISSING_RESPONSE_URL"}

