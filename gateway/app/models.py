from __future__ import annotations

from typing import Any

try:
    from pydantic import BaseModel, Field
except ModuleNotFoundError:
    class _FieldSpec:
        def __init__(self, *, default: Any = None, default_factory: Any = None) -> None:
            self.default = default
            self.default_factory = default_factory


    def Field(*, default: Any = None, default_factory: Any = None) -> Any:
        return _FieldSpec(default=default, default_factory=default_factory)


    class BaseModel:
        def __init__(self, **kwargs: Any) -> None:
            annotations = getattr(self.__class__, "__annotations__", {})
            for name in annotations:
                if name in kwargs:
                    value = kwargs[name]
                else:
                    if hasattr(self.__class__, name):
                        default = getattr(self.__class__, name)
                        if isinstance(default, _FieldSpec):
                            if default.default_factory is not None:
                                value = default.default_factory()
                            else:
                                value = default.default
                        else:
                            value = default
                    else:
                        raise TypeError(f"Missing required field: {name}")
                setattr(self, name, value)

        def model_dump(self) -> dict[str, Any]:
            return dict(self.__dict__)


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


class RepoView(BaseModel):
    repo: str
    code: str
    accepted_refs: list[str]
    path: str
    kind: str | None = None
    compose_service: str | None = None
    is_root: bool


class RepoCatalogView(BaseModel):
    root_repo: str
    repos: list[RepoView]
    available_codes: list[str]


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
