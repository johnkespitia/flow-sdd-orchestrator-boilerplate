from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .secrets_source import build_secret_source


@dataclass(frozen=True)
class Settings:
    workspace_root: Path
    database_path: Path
    flow_bin: str
    flow_entrypoint: str
    gateway_api_token: str | None
    slack_signing_secret: str | None
    github_webhook_secret: str | None
    jira_webhook_token: str | None
    default_feedback_provider: str | None
    worker_poll_interval: float
    enforce_approver_on_spec_approve_api: bool = False
    database_url: str | None = None

    @property
    def providers_manifest(self) -> Path:
        return self.workspace_root / "workspace.providers.json"


def load_settings() -> Settings:
    workspace_root = Path(os.getenv("FLOW_WORKSPACE_ROOT", ".")).resolve()
    database_path = Path(
        os.getenv("SOFTOS_GATEWAY_DB", str(workspace_root / "gateway" / "data" / "tasks.db"))
    ).resolve()
    database_url = os.getenv("SOFTOS_GATEWAY_DB_URL") or None
    secrets = build_secret_source(workspace_root=workspace_root)
    return Settings(
        workspace_root=workspace_root,
        database_path=database_path,
        database_url=database_url,
        flow_bin=os.getenv("SOFTOS_GATEWAY_FLOW_BIN", "python3"),
        flow_entrypoint=os.getenv("SOFTOS_GATEWAY_FLOW_ENTRYPOINT", "./flow"),
        gateway_api_token=secrets.get("SOFTOS_GATEWAY_API_TOKEN"),
        slack_signing_secret=secrets.get("SOFTOS_SLACK_SIGNING_SECRET"),
        github_webhook_secret=secrets.get("SOFTOS_GITHUB_WEBHOOK_SECRET"),
        jira_webhook_token=secrets.get("SOFTOS_JIRA_WEBHOOK_TOKEN"),
        default_feedback_provider=os.getenv("SOFTOS_DEFAULT_FEEDBACK_PROVIDER") or None,
        worker_poll_interval=float(os.getenv("SOFTOS_GATEWAY_POLL_INTERVAL", "0.5")),
        enforce_approver_on_spec_approve_api=str(os.getenv("SOFTOS_GATEWAY_ENFORCE_APPROVER_ON_SPEC_APPROVE", "") or "")
        .strip()
        .lower()
        in ("1", "true", "yes"),
    )
