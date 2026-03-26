from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from .config import Settings


def _load_feedback_section(settings: Settings) -> dict[str, Any]:
    if not settings.providers_manifest.is_file():
        return {
            "default_provider": "local-log",
            "providers": {
                "local-log": {
                    "enabled": True,
                    "entrypoint": "scripts/providers/feedback/local_log.sh",
                    "requires": [],
                }
            },
        }
    payload = json.loads(settings.providers_manifest.read_text(encoding="utf-8"))
    section = payload.get("feedback")
    if not isinstance(section, dict):
        raise RuntimeError("workspace.providers.json no define la seccion `feedback`.")
    providers = section.get("providers")
    if not isinstance(providers, dict) or not providers:
        raise RuntimeError("workspace.providers.json debe definir `feedback.providers`.")
    return section


def _provider_entrypoint(settings: Settings, config: dict[str, Any]) -> Path:
    entrypoint = str(config.get("entrypoint", "")).strip()
    if not entrypoint:
        raise RuntimeError("Feedback provider sin `entrypoint`.")
    return (settings.workspace_root / entrypoint).resolve()


def _feedback_message(task: dict[str, Any]) -> str:
    lines = [
        f"Task `{task['task_id']}`",
        f"Intent: `{task['intent']}`",
        f"Estado: `{task['status']}`",
    ]
    if task.get("exit_code") is not None:
        lines.append(f"Exit code: `{task['exit_code']}`")

    if task.get("parsed_output") is not None:
        parsed = json.dumps(task["parsed_output"], indent=2, ensure_ascii=True)
        lines.append("Salida estructurada:")
        lines.append(f"```json\n{parsed[:3000]}\n```")
    else:
        stdout = (task.get("stdout") or "").strip()
        stderr = (task.get("stderr") or "").strip()
        if stdout:
            lines.append("stdout:")
            lines.append(f"```\n{stdout[-3000:]}\n```")
        if stderr:
            lines.append("stderr:")
            lines.append(f"```\n{stderr[-3000:]}\n```")
    return "\n".join(lines)


def _resolve_provider(
    settings: Settings,
    section: dict[str, Any],
    response_target: dict[str, Any],
) -> tuple[str, dict[str, Any]] | None:
    providers = section["providers"]
    requested = str(response_target.get("provider", "")).strip()
    default_provider = (
        settings.default_feedback_provider
        or str(section.get("default_provider", "local-log")).strip()
        or "local-log"
    )

    for candidate in [requested, default_provider, "local-log"]:
        if not candidate:
            continue
        provider_config = providers.get(candidate)
        if not isinstance(provider_config, dict):
            continue
        if not bool(provider_config.get("enabled", True)):
            continue
        return candidate, provider_config
    return None


def send_feedback(settings: Settings, task: dict[str, Any]) -> dict[str, Any] | None:
    response_target = task.get("response_target") or {}
    if not isinstance(response_target, dict):
        response_target = {}

    section = _load_feedback_section(settings)
    resolved = _resolve_provider(settings, section, response_target)
    if resolved is None:
        return None
    provider_name, provider_config = resolved

    entrypoint = _provider_entrypoint(settings, provider_config)
    if not entrypoint.is_file():
        raise RuntimeError(f"Feedback provider sin entrypoint valido: {entrypoint}")

    env = os.environ.copy()
    for key, value in dict(provider_config.get("env", {})).items():
        env[str(key)] = str(value)
    env.update(
        {
            "FLOW_PROVIDER_CATEGORY": "feedback",
            "FLOW_PROVIDER_ACTION": "notify",
            "FLOW_PROVIDER_NAME": provider_name,
            "FLOW_WORKSPACE_ROOT": str(settings.workspace_root),
            "FLOW_WORKSPACE_PATH": str(settings.workspace_root),
            "FLOW_FEEDBACK_TASK_ID": task["task_id"],
            "FLOW_FEEDBACK_STATUS": task["status"],
            "FLOW_FEEDBACK_SOURCE": task["source"],
            "FLOW_FEEDBACK_INTENT": task["intent"],
            "FLOW_FEEDBACK_MESSAGE": _feedback_message(task),
            "FLOW_FEEDBACK_TARGET_KIND": str(response_target.get("kind", "")),
            "FLOW_GITHUB_COMMENTS_URL": str(response_target.get("comments_url", "")),
            "FLOW_SLACK_RESPONSE_URL": str(response_target.get("response_url", "")),
            "FLOW_JIRA_ISSUE_KEY": str(response_target.get("issue_key", "")),
        }
    )

    result = subprocess.run(
        ["bash", str(entrypoint)],
        cwd=settings.workspace_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "provider": provider_name,
        "return_code": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def send_feedback_event(
    settings: Settings,
    *,
    event: str,
    source: str,
    status: str,
    payload: dict[str, Any],
    response_target: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    section = _load_feedback_section(settings)
    target = response_target if isinstance(response_target, dict) else {}
    resolved = _resolve_provider(settings, section, target)
    if resolved is None:
        return None
    provider_name, provider_config = resolved
    entrypoint = _provider_entrypoint(settings, provider_config)
    if not entrypoint.is_file():
        raise RuntimeError(f"Feedback provider sin entrypoint valido: {entrypoint}")

    env = os.environ.copy()
    for key, value in dict(provider_config.get("env", {})).items():
        env[str(key)] = str(value)
    env.update(
        {
            "FLOW_PROVIDER_CATEGORY": "feedback",
            "FLOW_PROVIDER_ACTION": "notify",
            "FLOW_PROVIDER_NAME": provider_name,
            "FLOW_WORKSPACE_ROOT": str(settings.workspace_root),
            "FLOW_WORKSPACE_PATH": str(settings.workspace_root),
            "FLOW_FEEDBACK_EVENT": event,
            "FLOW_FEEDBACK_STATUS": status,
            "FLOW_FEEDBACK_SOURCE": source,
            "FLOW_FEEDBACK_MESSAGE": json.dumps({"event": event, "status": status, "payload": payload}, ensure_ascii=True),
            "FLOW_FEEDBACK_TARGET_KIND": str(target.get("kind", "")),
            "FLOW_GITHUB_COMMENTS_URL": str(target.get("comments_url", "")),
            "FLOW_SLACK_RESPONSE_URL": str(target.get("response_url", "")),
            "FLOW_JIRA_ISSUE_KEY": str(target.get("issue_key", "")),
        }
    )
    result = subprocess.run(
        ["bash", str(entrypoint)],
        cwd=settings.workspace_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "provider": provider_name,
        "return_code": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }
