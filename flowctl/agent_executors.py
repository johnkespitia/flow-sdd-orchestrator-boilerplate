from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

SUPPORTED_ADAPTERS = frozenset({"codex", "cursor", "opencode"})
EXECUTOR_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
AGENTS_SCHEMA_VERSION = 1
EXECUTOR_FIELDS = frozenset({"adapter", "executable", "argv", "transport", "allow_cli_fallback", "permission_policy", "acp"})
ACP_FIELDS = frozenset({"executable", "argv", "auth_method"})
TRANSPORTS = frozenset({"cli", "acp", "auto"})
PERMISSION_POLICIES = frozenset({"reject", "allow_once"})


@dataclass(frozen=True)
class AgentExecutor:
    executor_id: str
    adapter: str
    executable: str
    argv: tuple[str, ...]
    transport: str = "cli"
    allow_cli_fallback: bool = False
    permission_policy: str = "reject"
    acp_executable: str | None = None
    acp_argv: tuple[str, ...] = ()
    acp_auth_method: str | None = None


class AgentRegistryError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def load_json_object_with_duplicate_detection(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise AgentRegistryError(f"Falta {path.name} en el root del workspace.")
    try:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw, object_pairs_hook=_duplicate_key_detector)
    except json.JSONDecodeError as exc:
        raise AgentRegistryError(f"{path.name} no contiene JSON valido: {exc}") from exc
    if not isinstance(payload, dict):
        raise AgentRegistryError(f"{path.name} debe contener un objeto JSON en el root.")
    return payload


def _duplicate_key_detector(pairs: list[tuple[str, object]]) -> dict[str, object]:
    seen: set[str] = set()
    payload: dict[str, object] = {}
    for key, value in pairs:
        if key in seen:
            raise AgentRegistryError(f"Clave JSON duplicada: `{key}`.")
        seen.add(key)
        payload[key] = value
    return payload


def _validate_executor_executable(*, executor_id: str, executable: str) -> None:
    if Path(executable).is_absolute():
        return
    if "/" in executable or "\\" in executable or executable.startswith("."):
        raise AgentRegistryError(
            f"`agents.executors.{executor_id}.executable` debe ser un nombre ejecutable "
            f"o una ruta absoluta; recibido `{executable!r}`."
        )


def parse_agents_registry(workspace_config: dict[str, object]) -> dict[str, AgentExecutor]:
    agents = workspace_config.get("agents")
    if agents is None:
        raise AgentRegistryError("workspace.config.json debe definir la seccion `agents`.")
    if not isinstance(agents, dict):
        raise AgentRegistryError("`agents` debe ser un objeto.")

    schema_version = agents.get("schema_version")
    if type(schema_version) is not int or schema_version != AGENTS_SCHEMA_VERSION:
        raise AgentRegistryError(
            f"`agents.schema_version` debe ser {AGENTS_SCHEMA_VERSION}; recibido `{schema_version!r}`."
        )

    executors_raw = agents.get("executors")
    if not isinstance(executors_raw, dict) or not executors_raw:
        raise AgentRegistryError("`agents.executors` debe ser un objeto no vacio.")

    unknown_agents_fields = set(agents) - {"schema_version", "executors"}
    if unknown_agents_fields:
        field = sorted(unknown_agents_fields)[0]
        raise AgentRegistryError(f"Campo desconocido en `agents`: `{field}`.")

    executors: dict[str, AgentExecutor] = {}
    for executor_id, entry in executors_raw.items():
        if not EXECUTOR_ID_PATTERN.fullmatch(str(executor_id)):
            raise AgentRegistryError(
                f"ID de executor invalido `{executor_id}`; debe coincidir con ^[a-z0-9][a-z0-9-]*$."
            )
        if not isinstance(entry, dict):
            raise AgentRegistryError(f"`agents.executors.{executor_id}` debe ser un objeto.")

        unknown_fields = set(entry) - EXECUTOR_FIELDS
        if unknown_fields:
            field = sorted(unknown_fields)[0]
            raise AgentRegistryError(f"Campo desconocido en `agents.executors.{executor_id}`: `{field}`.")

        adapter = entry.get("adapter")
        if not isinstance(adapter, str) or not adapter.strip():
            raise AgentRegistryError(f"`agents.executors.{executor_id}.adapter` debe ser un string no vacio.")
        adapter = adapter.strip()
        if adapter not in SUPPORTED_ADAPTERS:
            raise AgentRegistryError(
                f"`agents.executors.{executor_id}.adapter` no soportado: `{adapter}`."
            )

        executable = entry.get("executable")
        if not isinstance(executable, str) or not executable.strip():
            raise AgentRegistryError(
                f"`agents.executors.{executor_id}.executable` debe ser un string no vacio."
            )
        executable = executable.strip()
        _validate_executor_executable(executor_id=str(executor_id), executable=executable)

        argv_raw = entry.get("argv")
        if not isinstance(argv_raw, list):
            raise AgentRegistryError(f"`agents.executors.{executor_id}.argv` debe ser un arreglo de strings.")
        argv: list[str] = []
        for index, item in enumerate(argv_raw):
            if not isinstance(item, str):
                raise AgentRegistryError(
                    f"`agents.executors.{executor_id}.argv[{index}]` debe ser un string."
                )
            argv.append(item)

        transport = entry.get("transport", "cli")
        if not isinstance(transport, str) or transport not in TRANSPORTS:
            raise AgentRegistryError(
                f"`agents.executors.{executor_id}.transport` invalido: `{transport!r}`."
            )
        allow_cli_fallback = entry.get("allow_cli_fallback", False)
        if not isinstance(allow_cli_fallback, bool):
            raise AgentRegistryError(
                f"`agents.executors.{executor_id}.allow_cli_fallback` debe ser booleano."
            )
        permission_policy = entry.get("permission_policy", "reject")
        if not isinstance(permission_policy, str) or permission_policy not in PERMISSION_POLICIES:
            raise AgentRegistryError(
                f"`agents.executors.{executor_id}.permission_policy` invalido: `{permission_policy!r}`."
            )

        acp_executable: str | None = None
        acp_argv: tuple[str, ...] = ()
        acp_auth_method: str | None = None
        acp_raw = entry.get("acp")
        if acp_raw is not None:
            if not isinstance(acp_raw, dict):
                raise AgentRegistryError(f"`agents.executors.{executor_id}.acp` debe ser un objeto.")
            unknown_acp = set(acp_raw) - ACP_FIELDS
            if unknown_acp:
                raise AgentRegistryError(
                    f"Campo desconocido en `agents.executors.{executor_id}.acp`: `{sorted(unknown_acp)[0]}`."
                )
            raw_acp_executable = acp_raw.get("executable")
            if raw_acp_executable is not None:
                if not isinstance(raw_acp_executable, str) or not raw_acp_executable.strip():
                    raise AgentRegistryError(
                        f"`agents.executors.{executor_id}.acp.executable` debe ser un string no vacio."
                    )
                acp_executable = raw_acp_executable.strip()
                _validate_executor_executable(executor_id=f"{executor_id}.acp", executable=acp_executable)
            raw_acp_argv = acp_raw.get("argv", [])
            if not isinstance(raw_acp_argv, list) or not all(isinstance(item, str) for item in raw_acp_argv):
                raise AgentRegistryError(f"`agents.executors.{executor_id}.acp.argv` debe ser un arreglo de strings.")
            acp_argv = tuple(raw_acp_argv)
            if acp_raw.get("auth_method") is not None:
                if not isinstance(acp_raw["auth_method"], str) or not acp_raw["auth_method"].strip():
                    raise AgentRegistryError(f"`agents.executors.{executor_id}.acp.auth_method` debe ser un string no vacio.")
                acp_auth_method = acp_raw["auth_method"].strip()

        executors[str(executor_id)] = AgentExecutor(
            executor_id=str(executor_id),
            adapter=adapter,
            executable=executable,
            argv=tuple(argv),
            transport=transport,
            allow_cli_fallback=allow_cli_fallback,
            permission_policy=permission_policy,
            acp_executable=acp_executable,
            acp_argv=acp_argv,
            acp_auth_method=acp_auth_method,
        )

    return dict(sorted(executors.items()))


def load_agent_registry(path: Path) -> dict[str, AgentExecutor]:
    workspace_config = load_json_object_with_duplicate_detection(path)
    return parse_agents_registry(workspace_config)


def executable_status(executable: str, *, shutil_which: Callable[[str], Optional[str]]) -> str:
    candidate = Path(executable)
    if candidate.is_absolute():
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return "ready"
        return "missing"
    if shutil_which(executable):
        return "ready"
    return "missing"


def command_agent_list(
    args,
    *,
    workspace_config_file: Path,
    json_dumps: Callable[[object], str],
) -> int:
    try:
        executors = load_agent_registry(workspace_config_file)
    except AgentRegistryError as exc:
        raise SystemExit(exc.message) from exc

    if bool(getattr(args, "json", False)):
        print(
            json_dumps(
                {
                    "executors": [
                        {
                            "id": item.executor_id,
                            "adapter": item.adapter,
                            "executable": item.executable,
                        }
                        for item in executors.values()
                    ]
                }
            )
        )
        return 0

    for item in executors.values():
        print(f"{item.executor_id}\tadapter={item.adapter}\texecutable={item.executable}")
    return 0


def command_agent_doctor(
    args,
    *,
    workspace_config_file: Path,
    shutil_which: Callable[[str], Optional[str]],
    json_dumps: Callable[[object], str],
) -> int:
    try:
        executors = load_agent_registry(workspace_config_file)
    except AgentRegistryError as exc:
        raise SystemExit(exc.message) from exc

    selected_id = getattr(args, "executor", None)
    if selected_id is not None:
        selected_id = str(selected_id).strip()
        if not selected_id:
            raise SystemExit("Debes indicar un executor valido o omitir el argumento.")
        if selected_id not in executors:
            raise SystemExit(f"Executor desconocido: `{selected_id}`.")

    targets = (
        [executors[selected_id]]
        if selected_id is not None
        else list(executors.values())
    )

    results = [
        {
            "id": item.executor_id,
            "adapter": item.adapter,
            "executable": item.executable,
            "status": executable_status(item.executable, shutil_which=shutil_which),
        }
        for item in targets
    ]

    if bool(getattr(args, "json", False)):
        print(json_dumps({"executors": results}))
    else:
        for item in results:
            print(
                f"{item['id']}\tadapter={item['adapter']}\texecutable={item['executable']}\tstatus={item['status']}"
            )

    return 0 if all(item["status"] == "ready" for item in results) else 1


def command_agent_run(
    args,
    *,
    workspace_root: Path,
    workspace_config_file: Path,
    workspace_config: dict[str, object],
    worktree_root: Path,
    root_repo: str,
    repo_names: list[str],
    shutil_which: Callable[[str], Optional[str]],
    subprocess_run: Callable[..., object],
    discover_free=None,
    discover_go=None,
    auth_evidence: object = None,
) -> int:
    # discover_free/discover_go default to None so production uses the OpenCode
    # probe boundary in agent_process_execution; tests may inject fixtures.
    from flowctl.agent_process_execution import AgentRunError, prepare_agent_run, run_agent_process

    try:
        prepared = prepare_agent_run(
            executor_id=str(getattr(args, "executor", "")),
            repo_raw=str(getattr(args, "repo", "")),
            workdir_raw=str(getattr(args, "workdir", "")),
            prompt_raw=str(getattr(args, "prompt", "")),
            target_raws=list(getattr(args, "target", []) or []),
            workspace_root=workspace_root,
            workspace_config_file=workspace_config_file,
            workspace_config=workspace_config,
            root_repo=root_repo,
        )
        exit_code, metadata = run_agent_process(
            executor=prepared.executor,
            repo=prepared.repo,
            workspace_root=workspace_root,
            workdir=prepared.workdir,
            targets=prepared.targets,
            prompt=prepared.prompt,
            shutil_which=shutil_which,
            subprocess_run=subprocess_run,
            resource_id=prepared.resource_id,
            resource=prepared.resource,
            discover_free=discover_free,
            discover_go=discover_go,
            auth_evidence=auth_evidence,
            model=getattr(args, "model", None),
            sandbox=getattr(args, "sandbox", None),
            transport=getattr(args, "transport", None),
        )
    except AgentRunError as exc:
        raise SystemExit(exc.message) from exc

    # ACP updates are written to stdout while evidence is written to stderr.
    # Flush first so merged terminal output preserves response-before-evidence order.
    sys.stdout.flush()
    print(
        "SOFTOS_EXECUTION_EVIDENCE "
        + json.dumps(
            {
                "executor": metadata.executor_id,
                "resource": metadata.resource_id,
                "transport_requested": metadata.transport_requested,
                "transport_used": metadata.transport_used,
                "acp_session_id": metadata.acp_session_id,
                "start_time": metadata.started_at,
                "end_time": metadata.finished_at,
                "result": metadata.result,
                "cancellation": metadata.cancellation,
                "permission_requests": metadata.permission_requests,
                "fallback_reason": metadata.fallback_reason,
                "failure_class": metadata.failure_class,
            },
            sort_keys=True,
        ),
        file=sys.stderr,
    )
    return exit_code
