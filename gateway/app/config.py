from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


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

    @property
    def providers_manifest(self) -> Path:
        return self.workspace_root / "workspace.providers.json"


def load_settings() -> Settings:
    workspace_root = Path(os.getenv("FLOW_WORKSPACE_ROOT", "/workspace")).resolve()
    database_path = Path(
        os.getenv("SOFTOS_GATEWAY_DB", str(workspace_root / "gateway" / "data" / "tasks.db"))
    ).resolve()
    return Settings(
        workspace_root=workspace_root,
        database_path=database_path,
        flow_bin=os.getenv("SOFTOS_GATEWAY_FLOW_BIN", "python3"),
        flow_entrypoint=os.getenv("SOFTOS_GATEWAY_FLOW_ENTRYPOINT", "./flow"),
        gateway_api_token=os.getenv("SOFTOS_GATEWAY_API_TOKEN") or None,
        slack_signing_secret=os.getenv("SOFTOS_SLACK_SIGNING_SECRET") or None,
        github_webhook_secret=os.getenv("SOFTOS_GITHUB_WEBHOOK_SECRET") or None,
        jira_webhook_token=os.getenv("SOFTOS_JIRA_WEBHOOK_TOKEN") or None,
        default_feedback_provider=os.getenv("SOFTOS_DEFAULT_FEEDBACK_PROVIDER") or None,
        worker_poll_interval=float(os.getenv("SOFTOS_GATEWAY_POLL_INTERVAL", "0.5")),
    )
