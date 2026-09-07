from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from flowctl.agent_executors import AgentExecutor

EXECUTION_CONTRACT_BEGIN = "---SOFTOS_EXECUTION_CONTRACT---"
EXECUTION_CONTRACT_END = "---SOFTOS_EXECUTION_CONTRACT_END---"

V1_ADAPTERS = frozenset({"codex", "cursor", "opencode"})

_GLOBAL_FORBIDDEN_STATIC_TOKENS = frozenset(
    {
        "--help",
        "-h",
        "--version",
        "-V",
        "--",
    }
)

_MODEL_PROVIDER_FORBIDDEN_TOKENS = frozenset(
    {
        "--model",
        "-m",
        "--provider",
        "--full-auto",
    }
)


@dataclass(frozen=True)
class _StaticArgvOption:
    names: frozenset[str]
    value_count: int


# V1 canonical registry entries use empty argv. Only explicitly reviewed,
# adapter-safe global options belong here; structural semantics stay adapter-owned.
_ADAPTER_ALLOWED_STATIC_OPTIONS: dict[str, tuple[_StaticArgvOption, ...]] = {
    "codex": (),
    "cursor": (),
    "opencode": (),
}

_ADAPTER_FORBIDDEN_STATIC_TOKENS: dict[str, frozenset[str]] = {
    "codex": frozenset(
        {
            "exec",
            "run",
            "--approve-for-me",
            "-p",
            "--prompt",
            "--trust",
            "--auto",
            *_MODEL_PROVIDER_FORBIDDEN_TOKENS,
        }
    ),
    "cursor": frozenset(
        {
            "exec",
            "run",
            "--trust",
            "-p",
            "--prompt",
            "--approve-for-me",
            "--auto",
            *_MODEL_PROVIDER_FORBIDDEN_TOKENS,
        }
    ),
    "opencode": frozenset(
        {
            "exec",
            "run",
            "--auto",
            "--dir",
            "-p",
            "--prompt",
            "--trust",
            "--approve-for-me",
            *_MODEL_PROVIDER_FORBIDDEN_TOKENS,
        }
    ),
}


class StaticArgvValidationError(ValueError):
    """Raised when configured executor.argv contains unsafe structural tokens."""


def validate_static_argv(adapter_name: str, static_argv: Sequence[str]) -> tuple[str, ...]:
    if adapter_name not in V1_ADAPTERS:
        raise StaticArgvValidationError(f"Adaptador no soportado: `{adapter_name}`.")

    if not static_argv:
        return ()

    forbidden = _GLOBAL_FORBIDDEN_STATIC_TOKENS | _ADAPTER_FORBIDDEN_STATIC_TOKENS[adapter_name]
    allowed_options = _ADAPTER_ALLOWED_STATIC_OPTIONS[adapter_name]
    allowed_by_name: dict[str, _StaticArgvOption] = {}
    for option in allowed_options:
        for name in option.names:
            allowed_by_name[name] = option

    validated: list[str] = []
    index = 0
    while index < len(static_argv):
        token = static_argv[index]
        if token in forbidden:
            raise StaticArgvValidationError(
                f"argv estatico no permitido para el adaptador `{adapter_name}`."
            )
        if token.startswith("-"):
            option = allowed_by_name.get(token)
            if option is None:
                raise StaticArgvValidationError(
                    f"argv estatico no permitido para el adaptador `{adapter_name}`."
                )
            validated.append(token)
            index += 1
            for _ in range(option.value_count):
                if index >= len(static_argv):
                    raise StaticArgvValidationError(
                        f"argv estatico no permitido para el adaptador `{adapter_name}`."
                    )
                validated.append(static_argv[index])
                index += 1
            continue
        raise StaticArgvValidationError(
            f"argv estatico no permitido para el adaptador `{adapter_name}`."
        )
    return tuple(validated)


@dataclass(frozen=True)
class AgentRunRequest:
    executor: AgentExecutor
    repo: str
    workspace_root: str
    workdir: str
    targets: tuple[str, ...]
    user_prompt: str
    contract_body: str
    model: str | None = None
    sandbox: str | None = None


@dataclass(frozen=True)
class AgentAdapterInvocation:
    argv: tuple[str, ...]
    stdin: str | None = None


class AgentExecutorAdapter(Protocol):
    adapter_name: str

    def build_invocation(self, request: AgentRunRequest) -> AgentAdapterInvocation:
        ...


def build_delivered_prompt(request: AgentRunRequest) -> str:
    return f"{request.contract_body}\n\n{request.user_prompt}"


def _build_positional_prompt_argv(
    request: AgentRunRequest,
    *,
    adapter_name: str,
    tail: tuple[str, ...],
    prompt: str,
) -> tuple[str, ...]:
    validated_static_argv = validate_static_argv(adapter_name, request.executor.argv)
    return (
        request.executor.executable,
        *validated_static_argv,
        *tail,
        "--",
        prompt,
    )


@dataclass(frozen=True)
class CodexAdapter:
    adapter_name: str = "codex"

    def build_invocation(self, request: AgentRunRequest) -> AgentAdapterInvocation:
        prompt = build_delivered_prompt(request)
        if request.model is not None or request.sandbox is not None:
            if request.model is not None and not request.model.strip():
                raise ValueError("El modelo Codex no puede estar vacio.")
            if request.sandbox is not None and request.sandbox not in {
                "read-only",
                "workspace-write",
                "danger-full-access",
            }:
                raise ValueError("El sandbox Codex debe ser read-only, workspace-write o danger-full-access.")
        codex_options: tuple[str, ...] = ()
        if request.model is not None:
            codex_options += ("-m", request.model.strip())
        if request.sandbox is not None:
            codex_options += ("-s", request.sandbox)
        argv = _build_positional_prompt_argv(
            request,
            adapter_name=self.adapter_name,
            tail=("exec", "--approve-for-me", *codex_options),
            prompt=prompt,
        )
        return AgentAdapterInvocation(argv=argv)


@dataclass(frozen=True)
class CursorAdapter:
    adapter_name: str = "cursor"

    def build_invocation(self, request: AgentRunRequest) -> AgentAdapterInvocation:
        prompt = build_delivered_prompt(request)
        argv = _build_positional_prompt_argv(
            request,
            adapter_name=self.adapter_name,
            tail=("--trust", "-p"),
            prompt=prompt,
        )
        return AgentAdapterInvocation(argv=argv)


@dataclass(frozen=True)
class OpenCodeAdapter:
    adapter_name: str = "opencode"

    def build_invocation(self, request: AgentRunRequest) -> AgentAdapterInvocation:
        prompt = build_delivered_prompt(request)
        argv = _build_positional_prompt_argv(
            request,
            adapter_name=self.adapter_name,
            tail=("run", "--auto", "--dir", request.workdir),
            prompt=prompt,
        )
        return AgentAdapterInvocation(argv=argv)


@dataclass(frozen=True)
class GenericStdinAdapter:
    """Test-oriented stdin transport for subprocess contract tests."""

    adapter_name: str

    def build_invocation(self, request: AgentRunRequest) -> AgentAdapterInvocation:
        delivered_prompt = build_delivered_prompt(request)
        argv = (request.executor.executable, *request.executor.argv)
        return AgentAdapterInvocation(argv=argv, stdin=delivered_prompt)


def build_execution_contract(*, request: AgentRunRequest) -> str:
    sorted_targets = "\n".join(f"  - {target}" for target in sorted(request.targets))
    repo_runtime = (
        f"python3 ./flow repo exec --workdir {request.workdir} {request.repo} -- <command>"
    )
    control_plane = "scripts/workspace_exec.sh python3 ./flow <command>"
    docker_lifecycle = "python3 ./flow stack <command>"
    body = "\n".join(
        [
            EXECUTION_CONTRACT_BEGIN,
            f"executor: {request.executor.executor_id}",
            f"repository: {request.repo}",
            f"workspace_root: {request.workspace_root}",
            f"workdir: {request.workdir}",
            "allowed_targets:",
            sorted_targets or "  -",
            "boundaries:",
            "  - reads and writes limited to the assigned repo/worktree",
            "  - writes limited to allowed_targets",
            "canonical_commands:",
            f"  - repo_runtime: {repo_runtime}",
            f"  - control_plane: {control_plane}",
            f"  - docker_lifecycle: {docker_lifecycle}",
            "notices:",
            "  - normal control-plane commands remain workspace-only; flow agent is host-native",
            "  - BMAD and workflow orchestration are outside this run's authority",
            EXECUTION_CONTRACT_END,
        ]
    )
    return body


_ADAPTERS: dict[str, AgentExecutorAdapter] = {
    "codex": CodexAdapter(),
    "cursor": CursorAdapter(),
    "opencode": OpenCodeAdapter(),
    "test": GenericStdinAdapter(adapter_name="test"),
}


def resolve_adapter(adapter_name: str) -> AgentExecutorAdapter:
    adapter = _ADAPTERS.get(adapter_name)
    if adapter is None:
        raise ValueError(f"Adapter no soportado: `{adapter_name}`.")
    return adapter
