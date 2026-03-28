from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .config import Settings
from .gateway_config import load_gateway_block


def _sleep(seconds: float) -> None:
    """Hook para tests (monkeypatch)."""
    time.sleep(seconds)


@dataclass(frozen=True)
class FeedbackRetryConfig:
    max_attempts: int = 4
    initial_delay_s: float = 0.5
    max_delay_s: float = 8.0
    backoff_multiplier: float = 2.0


def _default_retry_from_env() -> FeedbackRetryConfig:
    def _i(name: str, default: int) -> int:
        raw = str(os.getenv(name, "") or "").strip()
        if not raw:
            return default
        try:
            return max(1, int(raw))
        except ValueError:
            return default

    def _f(name: str, default: float) -> float:
        raw = str(os.getenv(name, "") or "").strip()
        if not raw:
            return default
        try:
            return float(raw)
        except ValueError:
            return default

    return FeedbackRetryConfig(
        max_attempts=_i("SOFTOS_FEEDBACK_RETRY_MAX_ATTEMPTS", 4),
        initial_delay_s=_f("SOFTOS_FEEDBACK_RETRY_INITIAL_DELAY_S", 0.5),
        max_delay_s=_f("SOFTOS_FEEDBACK_RETRY_MAX_DELAY_S", 8.0),
        backoff_multiplier=_f("SOFTOS_FEEDBACK_RETRY_BACKOFF_MULTIPLIER", 2.0),
    )


def _coerce_retry_dict(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return raw


def _merge_retry_config(
    base: FeedbackRetryConfig,
    *overlays: dict[str, Any],
) -> FeedbackRetryConfig:
    cfg = base
    for overlay in overlays:
        if not overlay:
            continue
        ma = cfg.max_attempts
        init_d = cfg.initial_delay_s
        max_d = cfg.max_delay_s
        mult = cfg.backoff_multiplier
        if "max_attempts" in overlay:
            raw = overlay["max_attempts"]
            if isinstance(raw, (int, float)):
                ma = int(raw)
        if "initial_delay_s" in overlay:
            raw = overlay["initial_delay_s"]
            if isinstance(raw, (int, float)):
                init_d = float(raw)
        if "max_delay_s" in overlay:
            raw = overlay["max_delay_s"]
            if isinstance(raw, (int, float)):
                max_d = float(raw)
        if "backoff_multiplier" in overlay:
            raw = overlay["backoff_multiplier"]
            if isinstance(raw, (int, float)):
                mult = float(raw)
        cfg = FeedbackRetryConfig(
            max_attempts=max(1, ma),
            initial_delay_s=max(0.0, init_d),
            max_delay_s=max(0.0, max_d),
            backoff_multiplier=max(1.0, mult),
        )
    return cfg


def _resolve_retry_config(
    settings: Settings,
    section: dict[str, Any],
    provider_config: dict[str, Any],
) -> FeedbackRetryConfig:
    base = _default_retry_from_env()
    global_overlay = _coerce_retry_dict(section.get("retry_policy"))
    provider_overlay = _coerce_retry_dict(provider_config.get("retry_policy"))
    return _merge_retry_config(base, global_overlay, provider_overlay)


def _is_permanent_feedback_failure(returncode: int, stderr: str) -> bool:
    """
    Convención: exit 2 o prefijo PERMANENT: en stderr => no reintentar.
    Cualquier otro código distinto de 0 se trata como transitorio (red/429/etc. simulado).
    """
    if returncode == 0:
        return False
    if returncode == 2:
        return True
    err = (stderr or "").strip()
    return err.startswith("PERMANENT:")


def _run_feedback_bash(
    entrypoint: Path,
    *,
    cwd: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(entrypoint)],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_with_retry(
    settings: Settings,
    section: dict[str, Any],
    provider_name: str,
    provider_config: dict[str, Any],
    run_once: Callable[[], subprocess.CompletedProcess[str]],
) -> dict[str, Any]:
    cfg = _resolve_retry_config(settings, section, provider_config)
    delay = cfg.initial_delay_s
    last: subprocess.CompletedProcess[str] | None = None
    for attempt in range(cfg.max_attempts):
        last = run_once()
        if last.returncode == 0:
            break
        if _is_permanent_feedback_failure(last.returncode, last.stderr):
            break
        if attempt + 1 >= cfg.max_attempts:
            break
        _sleep(min(delay, cfg.max_delay_s))
        delay = min(delay * cfg.backoff_multiplier, cfg.max_delay_s)
    assert last is not None
    return {
        "provider": provider_name,
        "return_code": last.returncode,
        "stdout": last.stdout.strip(),
        "stderr": last.stderr.strip(),
        "attempts_used": attempt + 1,
    }


def _load_feedback_section(settings: Settings) -> dict[str, Any]:
    if not settings.providers_manifest.is_file():
        return {
            "default_provider": "local-log",
            "retry_policy": {},
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


def _feedback_message(task: dict[str, Any], *, settings: Settings | None = None) -> str:
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
    base = "\n".join(lines)
    if settings is None:
        return base
    gw = load_gateway_block(settings.workspace_root)
    tmpl = gw.get("feedback_templates", {})
    intent = str(task.get("intent", ""))
    if isinstance(tmpl, dict) and intent in tmpl:
        try:
            return str(tmpl[intent]).format(
                task_id=task["task_id"],
                intent=intent,
                status=task["status"],
                body=base,
            )
        except Exception:
            return base
    return base


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
            "FLOW_FEEDBACK_MESSAGE": _feedback_message(task, settings=settings),
            "FLOW_FEEDBACK_TARGET_KIND": str(response_target.get("kind", "")),
            "FLOW_GITHUB_COMMENTS_URL": str(response_target.get("comments_url", "")),
            "FLOW_SLACK_RESPONSE_URL": str(response_target.get("response_url", "")),
            "FLOW_JIRA_ISSUE_KEY": str(response_target.get("issue_key", "")),
        }
    )

    def run_once() -> subprocess.CompletedProcess[str]:
        return _run_feedback_bash(entrypoint, cwd=settings.workspace_root, env=env)

    return _run_with_retry(settings, section, provider_name, provider_config, run_once)


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

    def run_once() -> subprocess.CompletedProcess[str]:
        return _run_feedback_bash(entrypoint, cwd=settings.workspace_root, env=env)

    return _run_with_retry(settings, section, provider_name, provider_config, run_once)
