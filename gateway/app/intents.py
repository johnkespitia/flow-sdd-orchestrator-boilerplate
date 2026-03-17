from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any

from .models import IntentRequest
from .repos import resolve_repo_references


class IntentError(ValueError):
    pass


def slugify(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    lowered = re.sub(r"-{2,}", "-", lowered)
    return lowered.strip("-")


def build_flow_command(intent: str, payload: dict[str, Any], *, workspace_root: Path) -> list[str]:
    if intent == "status.get":
        return ["status", "--json"]

    if intent == "spec.create":
        slug = slugify(str(payload.get("slug", "")))
        title = str(payload.get("title", "")).strip()
        try:
            repos = resolve_repo_references(payload, workspace_root=workspace_root)
        except ValueError as exc:
            raise IntentError(str(exc)) from exc
        if not slug or not title or not repos:
            raise IntentError("`spec.create` requiere `slug`, `title` y al menos un repo/codigo.")
        command = ["spec", "create", slug, "--title", title]
        for repo in repos:
            command.extend(["--repo", repo])
        for runtime in payload.get("required_runtimes", payload.get("runtimes", [])) or []:
            candidate = str(runtime).strip()
            if candidate:
                command.extend(["--runtime", candidate])
        for service in payload.get("required_services", payload.get("services", [])) or []:
            candidate = str(service).strip()
            if candidate:
                command.extend(["--service", candidate])
        for capability in payload.get("required_capabilities", payload.get("capabilities", [])) or []:
            candidate = str(capability).strip()
            if candidate:
                command.extend(["--capability", candidate])
        for dependency in payload.get("depends_on", []) or []:
            candidate = str(dependency).strip()
            if candidate:
                command.extend(["--depends-on", candidate])
        return command

    if intent == "spec.review":
        slug = slugify(str(payload.get("slug", "")))
        if not slug:
            raise IntentError("`spec.review` requiere `slug`.")
        return ["spec", "review", slug, "--json"]

    if intent == "spec.approve":
        slug = slugify(str(payload.get("slug", "")))
        if not slug:
            raise IntentError("`spec.approve` requiere `slug`.")
        command = ["spec", "approve", slug]
        approver = str(payload.get("approver", "")).strip()
        if approver:
            command.extend(["--approver", approver])
        return command

    if intent == "plan.create":
        slug = slugify(str(payload.get("slug", "")))
        if not slug:
            raise IntentError("`plan.create` requiere `slug`.")
        return ["plan", slug]

    if intent == "slice.verify":
        slug = slugify(str(payload.get("slug", "")))
        slice_name = str(payload.get("slice", "")).strip()
        if not slug or not slice_name:
            raise IntentError("`slice.verify` requiere `slug` y `slice`.")
        return ["slice", "verify", slug, slice_name]

    if intent == "ci.spec":
        return ["ci", "spec", "--all", "--json"]

    raise IntentError(f"Intent no soportado: {intent}")


def parse_text_command(text: str, *, source: str, reply_to: dict[str, Any] | None = None) -> IntentRequest:
    tokens = shlex.split(text)
    if not tokens:
        raise IntentError("No se recibieron tokens para el intent.")

    head = tokens.pop(0).lower()
    if head == "status":
        return IntentRequest(source=source, intent="status.get", payload={}, reply_to=reply_to)

    if head == "plan":
        if not tokens:
            raise IntentError("`plan` requiere un slug.")
        return IntentRequest(
            source=source,
            intent="plan.create",
            payload={"slug": tokens[0]},
            reply_to=reply_to,
        )

    if head == "spec":
        if len(tokens) < 2:
            raise IntentError("`spec` requiere una accion y un slug.")
        action = tokens.pop(0).lower()
        slug = tokens.pop(0)
        if action == "review":
            return IntentRequest(
                source=source,
                intent=f"spec.{action}",
                payload={"slug": slug},
                reply_to=reply_to,
            )
        if action == "approve":
            approver = None
            index = 0
            while index < len(tokens):
                token = tokens[index]
                if token == "--approver" and index + 1 < len(tokens):
                    approver = tokens[index + 1]
                    index += 2
                    continue
                raise IntentError(f"Flag no soportada en spec approve: {token}")
            payload = {"slug": slug}
            if approver:
                payload["approver"] = approver
            return IntentRequest(
                source=source,
                intent="spec.approve",
                payload=payload,
                reply_to=reply_to,
            )
        if action != "create":
            raise IntentError(f"Accion de spec no soportada: {action}")
        title = None
        repos: list[str] = []
        runtimes: list[str] = []
        services: list[str] = []
        capabilities: list[str] = []
        depends_on: list[str] = []
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if token == "--title" and index + 1 < len(tokens):
                title = tokens[index + 1]
                index += 2
                continue
            if token == "--repo" and index + 1 < len(tokens):
                repos.append(tokens[index + 1])
                index += 2
                continue
            if token == "--runtime" and index + 1 < len(tokens):
                runtimes.append(tokens[index + 1])
                index += 2
                continue
            if token == "--service" and index + 1 < len(tokens):
                services.append(tokens[index + 1])
                index += 2
                continue
            if token == "--capability" and index + 1 < len(tokens):
                capabilities.append(tokens[index + 1])
                index += 2
                continue
            if token == "--depends-on" and index + 1 < len(tokens):
                depends_on.append(tokens[index + 1])
                index += 2
                continue
            raise IntentError(f"Flag no soportada en spec create: {token}")
        return IntentRequest(
            source=source,
            intent="spec.create",
            payload={
                "slug": slug,
                "title": title or slug.replace("-", " ").title(),
                "repos": repos,
                "required_runtimes": runtimes,
                "required_services": services,
                "required_capabilities": capabilities,
                "depends_on": depends_on,
            },
            reply_to=reply_to,
        )

    if head == "slice":
        if len(tokens) < 3:
            raise IntentError("`slice` requiere accion, slug y slice.")
        action = tokens.pop(0).lower()
        if action != "verify":
            raise IntentError(f"Accion de slice no soportada: {action}")
        return IntentRequest(
            source=source,
            intent="slice.verify",
            payload={"slug": tokens[0], "slice": tokens[1]},
            reply_to=reply_to,
        )

    if head == "ci":
        if not tokens:
            raise IntentError("`ci` requiere una accion.")
        action = tokens.pop(0).lower()
        if action != "spec":
            raise IntentError(f"Accion de ci no soportada: {action}")
        return IntentRequest(source=source, intent="ci.spec", payload={}, reply_to=reply_to)

    raise IntentError(f"Comando no soportado: {head}")


def intent_from_github(event: str, payload: dict[str, Any]) -> IntentRequest | None:
    if event == "issue_comment":
        comment = payload.get("comment", {})
        body = str(comment.get("body", "")).strip()
        if not body.startswith("/flow "):
            return None
        issue = payload.get("issue", {})
        reply_to = {
            "kind": "github",
            "provider": "github-comment",
            "comments_url": issue.get("comments_url"),
            "issue_number": issue.get("number"),
            "repository": payload.get("repository", {}).get("full_name"),
        }
        return parse_text_command(body[len("/flow ") :], source="github", reply_to=reply_to)

    if event == "issues" and str(payload.get("action")) == "opened":
        issue = payload.get("issue", {})
        labels = [str(item.get("name", "")).strip() for item in issue.get("labels", []) if isinstance(item, dict)]
        if "flow-spec" not in labels:
            return None
        repos = [label.split(":", 1)[1] for label in labels if label.startswith("flow-repo:")]
        runtimes = [label.split(":", 1)[1] for label in labels if label.startswith("flow-runtime:")]
        services = [label.split(":", 1)[1] for label in labels if label.startswith("flow-service:")]
        capabilities = [label.split(":", 1)[1] for label in labels if label.startswith("flow-capability:")]
        depends_on = [label.split(":", 1)[1] for label in labels if label.startswith("flow-depends-on:")]
        title = str(issue.get("title", "")).strip() or str(issue.get("number", "feature"))
        slug = slugify(f"{issue.get('number', 'gh')}-{title}")
        reply_to = {
            "kind": "github",
            "provider": "github-comment",
            "comments_url": issue.get("comments_url"),
            "issue_number": issue.get("number"),
            "repository": payload.get("repository", {}).get("full_name"),
        }
        return IntentRequest(
            source="github",
            intent="spec.create",
            payload={
                "slug": slug,
                "title": title,
                "repos": repos,
                "required_runtimes": runtimes,
                "required_services": services,
                "required_capabilities": capabilities,
                "depends_on": depends_on,
            },
            reply_to=reply_to,
        )

    return None


def intent_from_jira(payload: dict[str, Any]) -> IntentRequest | None:
    explicit_intent = str(payload.get("intent", "")).strip()
    if explicit_intent:
        reply_to = payload.get("reply_to")
        if reply_to is not None and not isinstance(reply_to, dict):
            raise IntentError("`reply_to` en Jira debe ser un objeto si existe.")
        raw_payload = payload.get("payload", {})
        if not isinstance(raw_payload, dict):
            raise IntentError("`payload` en Jira debe ser un objeto.")
        return IntentRequest(source="jira", intent=explicit_intent, payload=raw_payload, reply_to=reply_to)

    issue = payload.get("issue")
    if not isinstance(issue, dict):
        return None

    fields = issue.get("fields", {})
    if not isinstance(fields, dict):
        fields = {}
    title = str(fields.get("summary", "")).strip()
    if not title:
        return None

    labels = [str(item).strip() for item in fields.get("labels", []) if str(item).strip()]
    repos = [label.split(":", 1)[1] for label in labels if label.startswith("flow-repo:")]
    runtimes = [label.split(":", 1)[1] for label in labels if label.startswith("flow-runtime:")]
    services = [label.split(":", 1)[1] for label in labels if label.startswith("flow-service:")]
    capabilities = [label.split(":", 1)[1] for label in labels if label.startswith("flow-capability:")]
    depends_on = [label.split(":", 1)[1] for label in labels if label.startswith("flow-depends-on:")]
    issue_key = str(issue.get("key", "")).strip()
    slug = slugify(f"{issue_key}-{title}") if issue_key else slugify(title)
    return IntentRequest(
        source="jira",
        intent="spec.create",
        payload={
            "slug": slug,
            "title": title,
            "repos": repos,
            "required_runtimes": runtimes,
            "required_services": services,
            "required_capabilities": capabilities,
            "depends_on": depends_on,
        },
        reply_to={
            "kind": "jira",
            "provider": "jira-comment",
            "issue_key": issue_key,
        },
    )
