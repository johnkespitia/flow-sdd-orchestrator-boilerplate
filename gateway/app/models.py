from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class IntentRequest(BaseModel):
    source: str = Field(default="api")
    intent: str
    payload: dict[str, Any] = Field(default_factory=dict)
    reply_to: dict[str, Any] | None = None


class TaskAccepted(BaseModel):
    task_id: str
    status: str
    intent: str
    source: str


class TaskView(BaseModel):
    task_id: str
    source: str
    intent: str
    status: str
    payload: dict[str, Any]
    command: list[str]
    response_target: dict[str, Any] | None = None
    stdout: str | None = None
    stderr: str | None = None
    exit_code: int | None = None
    parsed_output: Any | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    updated_at: str
