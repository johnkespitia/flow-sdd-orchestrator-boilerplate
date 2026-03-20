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


def _normalize_description(value: object) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in text.split("\n")]
    normalized = "\n".join(line for line in lines if line)
    return normalized.strip()


def _collect_jira_adf_text(value: object, chunks: list[str]) -> None:
    if isinstance(value, str):
        if value:
            chunks.append(value)
        return
    if isinstance(value, list):
        for item in value:
            _collect_jira_adf_text(item, chunks)
        return
    if not isinstance(value, dict):
        return

    node_type = str(value.get("type", "")).strip()
    if node_type == "hardBreak":
        chunks.append("\n")
        return
    if node_type == "listItem":
        chunks.append("- ")

    text = value.get("text")
    if isinstance(text, str) and text:
        chunks.append(text)

    content = value.get("content")
    if isinstance(content, list):
        for child in content:
            _collect_jira_adf_text(child, chunks)

    if node_type in {"paragraph", "heading", "listItem", "blockquote", "codeBlock"}:
        chunks.append("\n")


def _jira_description_text(value: object) -> str:
    if isinstance(value, str):
        return _normalize_description(value)
    if isinstance(value, dict):
        chunks: list[str] = []
        _collect_jira_adf_text(value, chunks)
        return _normalize_description("".join(chunks))
    return ""


def _normalize_acceptance_criteria(value: object) -> list[str]:
    if value is None:
        return []
    items: list[str] = []
    if isinstance(value, list):
        candidates = value
    else:
        candidates = [value]
    for candidate in candidates:
        if candidate is None:
            continue
        text = str(candidate).replace("\r\n", "\n").replace("\r", "\n")
        for line in text.split("\n"):
            normalized = line.strip().lstrip("-* ").strip()
            if normalized:
                items.append(normalized)
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def build_flow_command(intent: str, payload: dict[str, Any], *, workspace_root: Path) -> list[str]:
    if intent == "status.get":
        return ["status", "--json"]

    if intent in {"spec.create", "workflow.intake"}:
        slug = slugify(str(payload.get("slug", "")))
        title = str(payload.get("title", "")).strip()
        try:
            repos = resolve_repo_references(payload, workspace_root=workspace_root)
        except ValueError as exc:
            raise IntentError(str(exc)) from exc
        if not slug or not title or not repos:
            raise IntentError(f"`{intent}` requiere `slug`, `title` y al menos un repo/codigo.")
        command = ["workflow", "intake", slug, "--title", title] if intent == "workflow.intake" else ["spec", "create", slug, "--title", title]
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
        description = _normalize_description(payload.get("description", ""))
        if description:
            command.extend(["--description", description])
        for criterion in _normalize_acceptance_criteria(payload.get("acceptance_criteria")):
            command.extend(["--acceptance-criteria", criterion])
        command.append("--json")
        return command

    if intent == "workflow.next_step":
        slug = slugify(str(payload.get("slug", "")))
        if not slug:
            raise IntentError("`workflow.next_step` requiere `slug`.")
        return ["workflow", "next-step", slug, "--json"]

    if intent == "workflow.execute_feature":
        slug = slugify(str(payload.get("slug", "")))
        if not slug:
            raise IntentError("`workflow.execute_feature` requiere `slug`.")
        command = ["workflow", "execute-feature", slug, "--json"]
        if bool(payload.get("refresh_plan")):
            command.append("--refresh-plan")
        if bool(payload.get("start_slices")):
            command.append("--start-slices")
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

    if head == "workflow":
        if not tokens:
            raise IntentError("`workflow` requiere una accion.")
        action = tokens.pop(0).lower().replace("-", "_")
        if action == "next_step":
            if not tokens:
                raise IntentError("`workflow next-step` requiere un slug.")
            return IntentRequest(
                source=source,
                intent="workflow.next_step",
                payload={"slug": tokens[0]},
                reply_to=reply_to,
            )
        if action == "execute_feature":
            if not tokens:
                raise IntentError("`workflow execute-feature` requiere un slug.")
            slug = tokens.pop(0)
            refresh_plan = False
            start_slices = False
            index = 0
            while index < len(tokens):
                token = tokens[index]
                if token == "--refresh-plan":
                    refresh_plan = True
                    index += 1
                    continue
                if token == "--start-slices":
                    start_slices = True
                    index += 1
                    continue
                raise IntentError(f"Flag no soportada en workflow execute-feature: {token}")
            return IntentRequest(
                source=source,
                intent="workflow.execute_feature",
                payload={"slug": slug, "refresh_plan": refresh_plan, "start_slices": start_slices},
                reply_to=reply_to,
            )
        if action != "intake":
            raise IntentError(f"Accion de workflow no soportada: {action}")
        if not tokens:
            raise IntentError("`workflow intake` requiere un slug.")
        slug = tokens.pop(0)
        title = None
        repos: list[str] = []
        runtimes: list[str] = []
        services: list[str] = []
        capabilities: list[str] = []
        depends_on: list[str] = []
        description = None
        acceptance_criteria: list[str] = []
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
            if token == "--description" and index + 1 < len(tokens):
                description = tokens[index + 1]
                index += 2
                continue
            if token == "--acceptance-criteria" and index + 1 < len(tokens):
                acceptance_criteria.append(tokens[index + 1])
                index += 2
                continue
            raise IntentError(f"Flag no soportada en workflow intake: {token}")
        return IntentRequest(
            source=source,
            intent="workflow.intake",
            payload={
                "slug": slug,
                "title": title or slug.replace("-", " ").title(),
                "repos": repos,
                "required_runtimes": runtimes,
                "required_services": services,
                "required_capabilities": capabilities,
                "depends_on": depends_on,
                "description": _normalize_description(description),
                "acceptance_criteria": _normalize_acceptance_criteria(acceptance_criteria),
            },
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
        description = None
        acceptance_criteria: list[str] = []
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
            if token == "--description" and index + 1 < len(tokens):
                description = tokens[index + 1]
                index += 2
                continue
            if token == "--acceptance-criteria" and index + 1 < len(tokens):
                acceptance_criteria.append(tokens[index + 1])
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
                "description": _normalize_description(description),
                "acceptance_criteria": _normalize_acceptance_criteria(acceptance_criteria),
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
    def intake_from_issue(
        issue: dict[str, Any],
        *,
        repository_full_name: str,
        title_suffix: str = "",
        description_override: str = "",
        require_flow_spec_label: bool = True,
    ) -> IntentRequest | None:
        labels = [str(item.get("name", "")).strip() for item in issue.get("labels", []) if isinstance(item, dict)]
        if require_flow_spec_label and "flow-spec" not in labels:
            return None
        repos = [label.split(":", 1)[1] for label in labels if label.startswith("flow-repo:")]
        if not repos:
            repos = ["root"]
        runtimes = [label.split(":", 1)[1] for label in labels if label.startswith("flow-runtime:")]
        services = [label.split(":", 1)[1] for label in labels if label.startswith("flow-service:")]
        capabilities = [label.split(":", 1)[1] for label in labels if label.startswith("flow-capability:")]
        depends_on = [label.split(":", 1)[1] for label in labels if label.startswith("flow-depends-on:")]
        base_title = str(issue.get("title", "")).strip() or str(issue.get("number", "feature"))
        title = f"{base_title}{title_suffix}".strip()
        slug = slugify(f"{issue.get('number', 'gh')}-{title}")
        reply_to = {
            "kind": "github",
            "provider": "github-comment",
            "comments_url": issue.get("comments_url"),
            "issue_number": issue.get("number"),
            "repository": repository_full_name,
        }
        description = _normalize_description(description_override) or _normalize_description(issue.get("body", ""))
        return IntentRequest(
            source="github",
            intent="workflow.intake",
            payload={
                "slug": slug,
                "title": title,
                "repos": repos,
                "required_runtimes": runtimes,
                "required_services": services,
                "required_capabilities": capabilities,
                "depends_on": depends_on,
                "description": description,
            },
            reply_to=reply_to,
        )

    if event == "issue_comment":
        comment = payload.get("comment", {})
        body = str(comment.get("body", "")).strip()
        issue = payload.get("issue", {})
        repository_full_name = str(payload.get("repository", {}).get("full_name", "")).strip()
        reply_to = {
            "kind": "github",
            "provider": "github-comment",
            "comments_url": issue.get("comments_url"),
            "issue_number": issue.get("number"),
            "repository": repository_full_name,
        }

        if body.startswith("/flow "):
            return parse_text_command(body[len("/flow ") :], source="github", reply_to=reply_to)

        normalized = body.strip()
        lowered = normalized.lower()
        matches_spec_keyword = (
            lowered in {"/spec", "#spec", "flow-spec"}
            or lowered.startswith("/spec ")
            or lowered.startswith("#spec ")
            or lowered.startswith("flow-spec ")
        )
        if matches_spec_keyword:
            comment_context = normalized
            for prefix in ["/spec", "#spec", "flow-spec"]:
                if lowered.startswith(prefix):
                    comment_context = normalized[len(prefix):].strip()
                    break
            comment_id = str(comment.get("id", "")).strip()
            comment_number = issue.get("comments")
            suffix = ""
            if isinstance(comment_number, int) and comment_number > 0:
                suffix = f" - comment #{comment_number}"
            elif comment_id:
                suffix = f" - comment #{comment_id}"
            return intake_from_issue(
                issue,
                repository_full_name=repository_full_name,
                title_suffix=suffix,
                description_override=comment_context,
                require_flow_spec_label=False,
            )
        return None

    if event == "issues":
        action = str(payload.get("action", "")).strip()
        issue = payload.get("issue", {})
        repository_full_name = str(payload.get("repository", {}).get("full_name", "")).strip()
        if not isinstance(issue, dict):
            return None
        if action == "opened":
            return intake_from_issue(issue, repository_full_name=repository_full_name)
        if action == "labeled":
            label_name = str(payload.get("label", {}).get("name", "")).strip()
            if label_name != "flow-spec":
                return None
            return intake_from_issue(issue, repository_full_name=repository_full_name)

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
    description = _jira_description_text(fields.get("description"))
    acceptance_criteria = _normalize_acceptance_criteria(
        fields.get("acceptance_criteria", fields.get("acceptanceCriteria"))
    )
    slug = slugify(f"{issue_key}-{title}") if issue_key else slugify(title)
    payload_out: dict[str, Any] = {
        "slug": slug,
        "title": title,
        "repos": repos,
        "required_runtimes": runtimes,
        "required_services": services,
        "required_capabilities": capabilities,
        "depends_on": depends_on,
    }
    if description:
        payload_out["description"] = description
    if acceptance_criteria:
        payload_out["acceptance_criteria"] = acceptance_criteria
    return IntentRequest(
        source="jira",
        intent="workflow.intake",
        payload=payload_out,
        reply_to={
            "kind": "jira",
            "provider": "jira-comment",
            "issue_key": issue_key,
        },
    )
