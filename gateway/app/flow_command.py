"""Construcción de comandos `flow` a partir de intents (T19: separado del parseo en `intents.py`)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .intent_utils import (
    IntentError,
    _normalize_acceptance_criteria,
    _normalize_description,
    slugify,
)
from .repos import resolve_repo_references


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
                command.extend(["--depends-on", dependency])
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
