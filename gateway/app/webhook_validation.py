from __future__ import annotations

from typing import Any


def validate_github_payload(event: str, payload: Any) -> tuple[bool, str, str]:
    if not isinstance(payload, dict):
        return False, "INVALID_JSON", "GitHub payload must be a JSON object."
    if not isinstance(event, str) or not event.strip():
        return False, "MISSING_EVENT", "Missing x-github-event header."
    if event not in {"issues", "issue_comment", "pull_request"}:
        return False, "UNSUPPORTED_EVENT", f"Unsupported GitHub event: {event}"
    if "repository" not in payload or not isinstance(payload.get("repository"), dict):
        return False, "MISSING_REPOSITORY", "Missing repository field."
    if event == "issues":
        if "action" not in payload:
            return False, "MISSING_ACTION", "Missing action field."
        if "issue" not in payload or not isinstance(payload.get("issue"), dict):
            return False, "MISSING_ISSUE", "Missing issue field."
    if event == "issue_comment":
        if "comment" not in payload or not isinstance(payload.get("comment"), dict):
            return False, "MISSING_COMMENT", "Missing comment field."
        if "issue" not in payload or not isinstance(payload.get("issue"), dict):
            return False, "MISSING_ISSUE", "Missing issue field."
    if event == "pull_request":
        if "action" not in payload:
            return False, "MISSING_ACTION", "Missing action field."
        if "pull_request" not in payload or not isinstance(payload.get("pull_request"), dict):
            return False, "MISSING_PULL_REQUEST", "Missing pull_request field."
    return True, "", ""


def validate_jira_payload(payload: Any) -> tuple[bool, str, str]:
    if not isinstance(payload, dict):
        return False, "INVALID_JSON", "Jira payload must be a JSON object."
    # Two supported shapes: explicit intent wrapper or issue webhook.
    if str(payload.get("intent", "")).strip():
        raw = payload.get("payload")
        if raw is not None and not isinstance(raw, dict):
            return False, "INVALID_PAYLOAD", "`payload` must be an object."
        reply_to = payload.get("reply_to")
        if reply_to is not None and not isinstance(reply_to, dict):
            return False, "INVALID_REPLY_TO", "`reply_to` must be an object."
        return True, "", ""
    issue = payload.get("issue")
    if not isinstance(issue, dict):
        return False, "MISSING_ISSUE", "Missing issue field."
    fields = issue.get("fields")
    if fields is not None and not isinstance(fields, dict):
        return False, "INVALID_FIELDS", "Issue fields must be an object."
    fields = fields if isinstance(fields, dict) else {}
    title = str(fields.get("summary", "")).strip()
    if not title:
        return False, "MISSING_SUMMARY", "Missing issue summary."
    return True, "", ""


def validate_slack_command(form: dict[str, Any]) -> tuple[bool, str, str]:
    # Slack sends form-encoded payload. For our purposes enforce basic required fields.
    text = str(form.get("text", "")).strip()
    response_url = str(form.get("response_url", "")).strip()
    if str(form.get("ssl_check", "")).strip() == "1":
        return True, "", ""
    if not text:
        return False, "MISSING_TEXT", "Missing slack command text."
    if not response_url:
        return False, "MISSING_RESPONSE_URL", "Missing slack response_url."
    return True, "", ""

