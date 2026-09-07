from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence

from flowctl.agent_executor_adapters import (
    AgentAdapterInvocation,
    AgentRunRequest,
    build_execution_contract,
    resolve_adapter,
)
from flowctl.agent_executors import AgentExecutor, AgentRegistryError, load_agent_registry
from flowctl.agent_resources import (
    AgentResource,
    AgentResourceError,
    DiscoverModelsFn,
    parse_resource_registry,
    resolve_free_model,
    resolve_go_model,
)

# Process-local OpenCode config overlay key (never persisted to Git/evidence).
OPENCODE_CONFIG_CONTENT_ENV = "OPENCODE_CONFIG_CONTENT"

# Local machine OpenCode config carriers scrubbed for Free/Go so cloud runs do not
# inherit worker/profile/model/provider configuration from the local resource path.
CLOUD_SCRUB_ENV_KEYS = frozenset(
    {
        "OPENCODE_CONFIG",
        "OPENCODE_CONFIG_CONTENT",
        "OPENCODE_CONFIG_DIR",
    }
)

_FORBIDDEN_OVERLAY_ENV_KEY_RE = re.compile(
    r"(TOKEN|SECRET|CREDENTIAL|PASSWORD|PASSWD|API[_-]?KEY|AUTH)",
    re.IGNORECASE,
)

FORBIDDEN_CONFIG_CONTENT_KEYS = frozenset(
    {
        "token",
        "tokens",
        "credential",
        "credentials",
        "secret",
        "secrets",
        "api_key",
        "api_keys",
        "apiKey",
        "apiKeys",
        "password",
        "passwd",
        "auth",
        "authorization",
        "provider",
        "providers",
        "openai_api_key",
        "anthropic_api_key",
    }
)

LOCAL_WORKER_AGENT = "softos-local-worker"

# Production Free/Go discovery uses a bounded OpenCode CLI probe. Injectable in tests.
OPENCODE_MODELS_PROBE_ARGV = ("models",)
OPENCODE_MODELS_PROBE_TIMEOUT_SECONDS = 20.0
_DEFAULT_OPENCODE_EXECUTABLE = "opencode"


class AgentRunError(Exception):
    def __init__(self, message: str, *, exit_code: int = 1) -> None:
        self.message = message
        self.exit_code = exit_code
        super().__init__(message)


@dataclass(frozen=True)
class AgentRunMetadata:
    executor_id: str
    repo: str
    workdir: str
    targets: tuple[str, ...]
    started_at: str
    finished_at: str
    exit_code: int
    resource_id: Optional[str] = None


@dataclass(frozen=True)
class PreparedAgentRun:
    """Prepared run inputs.

    Unpacks as the legacy 5-tuple ``(executor, repo, workdir, targets, prompt)`` so
    existing callers (including adapter tests outside this PU) keep working, while
    exposing ``resource_id`` / ``resource`` for harness overlay propagation.
    """

    executor: AgentExecutor
    repo: str
    workdir: Path
    targets: tuple[str, ...]
    prompt: str
    resource_id: Optional[str] = None
    resource: Optional[AgentResource] = None

    def __iter__(self):
        yield self.executor
        yield self.repo
        yield self.workdir
        yield self.targets
        yield self.prompt

    def __len__(self) -> int:
        return 5

    def __getitem__(self, index: int):
        return (self.executor, self.repo, self.workdir, self.targets, self.prompt)[index]


def path_is_contained(child: Path, parent: Path) -> bool:
    parent_canonical = parent.resolve()
    try:
        child.resolve().relative_to(parent_canonical)
        return True
    except (ValueError, OSError):
        return False


def list_registered_worktree_paths(
    repo_root: Path,
    *,
    run_git: Callable[..., object] = subprocess.run,
) -> frozenset[Path]:
    completed = run_git(
        ["git", "-C", str(repo_root), "worktree", "list", "--porcelain"],
        capture_output=True,
        check=False,
    )
    if int(getattr(completed, "returncode", 1)) != 0:
        raise AgentRunError(
            "No pude consultar los worktrees registrados de git para el repo seleccionado."
        )
    stdout = getattr(completed, "stdout", b"")
    if isinstance(stdout, bytes):
        text = stdout.decode("utf-8", errors="replace")
    else:
        text = str(stdout or "")
    paths: list[Path] = []
    for line in text.splitlines():
        if line.startswith("worktree "):
            paths.append(Path(line[len("worktree "):].strip()).resolve())
    return frozenset(paths)


def resolve_repo_id(raw_repo: str, *, repos: dict[str, object], root_repo: str) -> str:
    candidate = raw_repo.strip()
    if not candidate:
        raise AgentRunError("Debes indicar `--repo`.")
    if candidate in repos:
        return candidate
    if candidate == "workspace-root":
        return root_repo
    root_aliases = {"root", "root-repo", "root_repo", "workspace", "."}
    if candidate in root_aliases:
        return root_repo
    raise AgentRunError(f"Repo desconocido: `{candidate}`.")


def resolve_repo_root(repo: str, *, workspace_root: Path, repos: dict[str, object], root_repo: str) -> Path:
    config = repos.get(repo)
    if not isinstance(config, dict):
        raise AgentRunError(f"Repo desconocido: `{repo}`.")
    relative = str(config.get("path", ".")).strip()
    if repo == root_repo or relative in {"", "."}:
        return workspace_root
    return workspace_root / relative


def validate_workdir(
    raw_workdir: str,
    *,
    workspace_root: Path,
    repo_root_path: Path,
    run_git: Callable[..., object] = subprocess.run,
) -> Path:
    candidate = raw_workdir.strip()
    if not candidate:
        raise AgentRunError("Debes indicar `--workdir`.")
    workdir_path = Path(candidate)
    if not workdir_path.exists():
        raise AgentRunError(f"El workdir no existe: `{candidate}`.")
    if not workdir_path.is_dir():
        raise AgentRunError(f"El workdir debe ser un directorio: `{candidate}`.")

    canonical = workdir_path.resolve()
    workspace_canonical = workspace_root.resolve()
    if not path_is_contained(canonical, workspace_canonical):
        raise AgentRunError(f"El workdir queda fuera del workspace: `{candidate}`.")

    repo_canonical = repo_root_path.resolve()
    if canonical == repo_canonical:
        return canonical

    registered = list_registered_worktree_paths(repo_root_path, run_git=run_git)
    if canonical not in registered:
        raise AgentRunError(
            f"El workdir no es el root del repo ni un worktree reconocido: `{candidate}`."
        )
    return canonical


def resolve_target_within_workdir(workdir: Path, raw_target: str) -> str:
    target_text = raw_target.strip()
    if not target_text:
        raise AgentRunError("Cada `--target` debe ser un path no vacio.")

    target_path = Path(target_text)
    if target_path.is_absolute():
        raise AgentRunError(f"Target fuera de limites: `{target_text}`.")

    normalized = os.path.normpath(target_text)
    if normalized in {".", ""}:
        parts: list[str] = []
    else:
        parts = [part for part in Path(normalized).parts if part and part != "."]

    if ".." in parts:
        raise AgentRunError(f"Target fuera de limites: `{target_text}`.")

    root_real = workdir.resolve()
    current = workdir

    for part in parts:
        current = current / part
        try:
            resolved = current.resolve(strict=False)
        except (OSError, RuntimeError):
            raise AgentRunError(f"Target fuera de limites: `{target_text}`.")
        try:
            resolved.relative_to(root_real)
        except ValueError:
            raise AgentRunError(f"Target fuera de limites: `{target_text}`.")

    if parts:
        return Path(*parts).as_posix()
    return "."


def normalize_targets(workdir: Path, raw_targets: Sequence[str]) -> tuple[str, ...]:
    if not raw_targets:
        raise AgentRunError("Debes indicar al menos un `--target`.")
    normalized = sorted({resolve_target_within_workdir(workdir, item) for item in raw_targets})
    return tuple(normalized)


def validate_prompt(raw_prompt: str) -> str:
    if not raw_prompt.strip():
        raise AgentRunError("Debes indicar un `--prompt` no vacio.")
    return raw_prompt


def executable_is_ready(executable: str, *, shutil_which: Callable[[str], Optional[str]]) -> bool:
    candidate = Path(executable)
    if candidate.is_absolute():
        return candidate.is_file() and os.access(candidate, os.X_OK)
    return shutil_which(executable) is not None


def _child_stream_bytes(payload: object) -> bytes:
    if payload is None:
        return b""
    if isinstance(payload, bytes):
        return payload
    return str(payload).encode("utf-8")


def _is_forbidden_overlay_env_key(key: str) -> bool:
    return _FORBIDDEN_OVERLAY_ENV_KEY_RE.search(key) is not None


def _validate_config_content_object(payload: object, *, path: str = "OPENCODE_CONFIG_CONTENT") -> None:
    if not isinstance(payload, dict):
        raise AgentRunError(f"`{path}` del overlay debe ser un objeto JSON.")
    for key, value in payload.items():
        key_text = str(key)
        if key_text in FORBIDDEN_CONFIG_CONTENT_KEYS or _is_forbidden_overlay_env_key(key_text):
            raise AgentRunError(
                f"Overlay de proceso rechazado: campo prohibido `{key_text}` en `{path}` "
                "(credenciales/auth/provider payloads no son permitidos)."
            )
        if isinstance(value, dict):
            _validate_config_content_object(value, path=f"{path}.{key_text}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, (dict, list)):
                    _validate_config_content_object(item, path=f"{path}.{key_text}[{index}]")


def validate_process_env_overlay(overlay: Mapping[str, object]) -> dict[str, str]:
    """Validate a process-local env overlay before merge/launch.

    Rejects credential/token/secret/auth keys and raw provider payloads inside
    ``OPENCODE_CONFIG_CONTENT``. Does not persist the overlay.
    """
    if not isinstance(overlay, Mapping):
        raise AgentRunError("El overlay de entorno debe ser un mapping.")
    validated: dict[str, str] = {}
    for raw_key, raw_value in overlay.items():
        if not isinstance(raw_key, str) or not raw_key.strip():
            raise AgentRunError("Las claves del overlay de entorno deben ser strings no vacios.")
        key = raw_key.strip()
        if _is_forbidden_overlay_env_key(key):
            raise AgentRunError(
                f"Overlay de proceso rechazado: clave de entorno prohibida `{key}`."
            )
        if not isinstance(raw_value, str):
            raise AgentRunError(
                f"Overlay de proceso rechazado: valor de `{key}` debe ser string."
            )
        if key == OPENCODE_CONFIG_CONTENT_ENV:
            try:
                parsed = json.loads(raw_value)
            except json.JSONDecodeError as exc:
                raise AgentRunError(
                    f"`{OPENCODE_CONFIG_CONTENT_ENV}` del overlay no es JSON valido."
                ) from exc
            _validate_config_content_object(parsed)
            if isinstance(parsed, dict):
                default_agent = parsed.get("default_agent")
                if isinstance(default_agent, str) and default_agent.strip() == LOCAL_WORKER_AGENT:
                    # Cloud overlays must never smuggle the local worker/profile.
                    # Local resource path uses empty overlay and inherits operator config.
                    model = parsed.get("model")
                    if isinstance(model, str) and model.strip():
                        raise AgentRunError(
                            "Overlay de proceso rechazado: no se puede combinar "
                            f"`default_agent={LOCAL_WORKER_AGENT}` con model cloud resuelto."
                        )
        validated[key] = raw_value
    return validated


def merge_process_environment(
    inherited: Mapping[str, str],
    overlay: Mapping[str, str],
    *,
    scrub_keys: frozenset[str] = frozenset(),
) -> dict[str, str]:
    """Merge a validated overlay onto a copy of the inherited environment.

    Never replaces the inherited environment wholesale: starts from a copy, optionally
    scrubs local-config carriers, then applies overlay keys.
    """
    validated = validate_process_env_overlay(overlay)
    merged = dict(inherited)
    for key in scrub_keys:
        merged.pop(key, None)
    merged.update(validated)
    return merged


def build_resource_process_overlay(
    resource: AgentResource,
    *,
    model_id: Optional[str] = None,
) -> tuple[dict[str, str], frozenset[str]]:
    """Build a resource-specific process overlay and scrub set.

    - ``worker_profile`` (local): empty overlay; preserve inherited worker/profile contract.
    - ``dynamic_free`` / ``dynamic_go``: set ``OPENCODE_CONFIG_CONTENT`` with the resolved
      model only; scrub local OpenCode config carriers so Free/Go do not inherit local
      worker/profile/model/provider configuration.
    """
    if resource.model_resolution == "worker_profile":
        return {}, frozenset()

    if resource.model_resolution not in {"dynamic_free", "dynamic_go"}:
        raise AgentRunError(
            f"Resource `{resource.resource_id}` usa model_resolution no soportado en overlay."
        )
    if not isinstance(model_id, str) or not model_id.strip():
        raise AgentRunError(
            f"Resource `{resource.resource_id}` requiere un model_id resuelto para el overlay."
        )
    content = json.dumps({"model": model_id.strip()}, separators=(",", ":"), sort_keys=True)
    overlay = {OPENCODE_CONFIG_CONTENT_ENV: content}
    return overlay, CLOUD_SCRUB_ENV_KEYS


def _extract_model_ids_from_json(payload: object) -> list[str]:
    """Extract model id strings only; never retain provider/auth payloads."""
    found: list[str] = []
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, str) and item.strip():
                found.append(item.strip())
            elif isinstance(item, dict):
                for key in ("id", "model", "modelID", "model_id"):
                    value = item.get(key)
                    if isinstance(value, str) and value.strip():
                        found.append(value.strip())
                        break
        return found
    if isinstance(payload, dict):
        models = payload.get("models")
        if isinstance(models, (dict, list)):
            found.extend(_extract_model_ids_from_json(models))
        for key, value in payload.items():
            if key == "models":
                continue
            if isinstance(value, dict):
                nested_models = value.get("models")
                if isinstance(nested_models, (dict, list)):
                    found.extend(_extract_model_ids_from_json(nested_models))
                    continue
                model_id = value.get("id")
                if isinstance(model_id, str) and model_id.strip():
                    # Prefer nested id when the entry looks like a model record.
                    if any(field in value for field in ("name", "family", "cost", "limit")):
                        found.append(model_id.strip())
                        continue
            if isinstance(key, str) and key.strip() and ("/" in key or key.endswith("-free")):
                found.append(key.strip())
    return found


def _extract_model_ids_from_probe_output(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if parsed is not None:
        return _extract_model_ids_from_json(parsed)

    ids: list[str] = []
    for line in text.splitlines():
        candidate = line.strip()
        if not candidate or candidate.startswith("#"):
            continue
        candidate_id = candidate.split()[0].strip()
        if not candidate_id:
            continue
        if candidate_id.lower() in {"model", "models", "id", "name", "provider", "providers"}:
            continue
        if _FORBIDDEN_OVERLAY_ENV_KEY_RE.search(candidate_id):
            continue
        ids.append(candidate_id)
    return ids


def probe_opencode_models(
    *,
    executable: str = _DEFAULT_OPENCODE_EXECUTABLE,
    subprocess_run: Callable[..., object] = subprocess.run,
    timeout_seconds: float = OPENCODE_MODELS_PROBE_TIMEOUT_SECONDS,
) -> list[str]:
    """Bounded OpenCode-compatible model discovery probe.

    Runs ``opencode models`` and returns model id strings only. Does not persist
    credentials, auth payloads, or raw provider responses.
    """
    exe = executable.strip() if isinstance(executable, str) else ""
    if not exe:
        raise RuntimeError("opencode_models_probe_missing_executable")
    try:
        completed = subprocess_run(
            [exe, *OPENCODE_MODELS_PROBE_ARGV],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001 - mapped by resolve_*_model to UNKNOWN
        raise RuntimeError(f"opencode_models_probe_error:{exc.__class__.__name__}") from exc

    if int(getattr(completed, "returncode", 1)) != 0:
        raise RuntimeError("opencode_models_probe_failed")

    stdout = getattr(completed, "stdout", "") or ""
    if isinstance(stdout, bytes):
        stdout = stdout.decode("utf-8", errors="replace")
    return _extract_model_ids_from_probe_output(str(stdout))


def default_opencode_model_discovery() -> list[str]:
    """Production default DiscoverModelsFn for Free/Go when callers omit hooks."""
    return probe_opencode_models()


def resolve_resource_model(
    resource: AgentResource,
    *,
    discover_free: Optional[DiscoverModelsFn] = None,
    discover_go: Optional[DiscoverModelsFn] = None,
    auth_evidence: object = None,
    default_discover: Optional[DiscoverModelsFn] = None,
) -> Optional[str]:
    """Resolve Free/Go model via discovery; local leaves model unset.

    When callers omit ``discover_free`` / ``discover_go``, the production default
    OpenCode probe is used. Tests may inject either hook or ``default_discover``.
    Go remains AUTH_UNCONFIGURED without valid auth evidence (checked before discover).
    """
    if resource.model_resolution == "worker_profile":
        return None

    production_discover = default_discover or default_opencode_model_discovery

    if resource.model_resolution == "dynamic_free":
        discover = discover_free if discover_free is not None else production_discover
        result = resolve_free_model(discover=discover, tie_break=resource.candidate_tie_break)
        if result.availability != "AVAILABLE" or not result.model_id:
            reason = result.reason or result.availability
            raise AgentRunError(
                f"Resource `{resource.resource_id}` no puede lanzarse: `{reason}`."
            )
        return result.model_id

    if resource.model_resolution == "dynamic_go":
        discover = discover_go if discover_go is not None else production_discover
        result = resolve_go_model(
            discover=discover,
            auth_evidence=auth_evidence,
            tie_break=resource.candidate_tie_break,
        )
        if result.availability == "AUTH_UNCONFIGURED":
            raise AgentRunError(
                f"Resource `{resource.resource_id}` no puede lanzarse: `AUTH_UNCONFIGURED`."
            )
        if result.availability != "AVAILABLE" or not result.model_id:
            reason = result.reason or result.availability
            raise AgentRunError(
                f"Resource `{resource.resource_id}` no puede lanzarse: `{reason}`."
            )
        return result.model_id

    raise AgentRunError(
        f"Resource `{resource.resource_id}` usa model_resolution no soportado."
    )


def resolve_agent_selector(
    selector: str,
    *,
    executors: Mapping[str, AgentExecutor],
    workspace_config: Mapping[str, object],
) -> tuple[AgentExecutor, Optional[str], Optional[AgentResource]]:
    """Resolve positional selection as logical resource first, then executor.

    Preserves legacy ``flow agent run <executor-id>`` when the selector is only an
    executor ID. Does not add a ``--resource`` flag.
    """
    selected_id = selector.strip()
    if not selected_id:
        raise AgentRunError("Debes indicar un executor.")

    resources: dict[str, AgentResource] = {}
    if "agent_resources" in workspace_config:
        try:
            resources = parse_resource_registry(workspace_config, executors=executors)
        except AgentResourceError as exc:
            raise AgentRunError(exc.message) from exc

    if selected_id in resources:
        resource = resources[selected_id]
        executor = executors.get(resource.executor_id)
        if executor is None:
            raise AgentRunError(
                f"Resource `{selected_id}` referencia executor inexistente "
                f"`{resource.executor_id}`."
            )
        return executor, resource.resource_id, resource

    executor = executors.get(selected_id)
    if executor is None:
        raise AgentRunError(f"Executor desconocido: `{selected_id}`.")
    return executor, None, None


def execute_subprocess(
    invocation: AgentAdapterInvocation,
    *,
    cwd: Path,
    subprocess_run: Callable[..., object] = subprocess.run,
    env_overlay: Mapping[str, str] | None = None,
    scrub_env_keys: frozenset[str] = frozenset(),
    inherited_env: Mapping[str, str] | None = None,
) -> tuple[int, bytes, bytes]:
    kwargs: dict[str, object] = {
        "args": list(invocation.argv),
        "cwd": str(cwd),
        "shell": False,
        "capture_output": True,
    }
    if invocation.stdin is not None:
        kwargs["input"] = invocation.stdin.encode("utf-8")

    # Resource-specific configuration is applied only here: validate + merge onto a
    # copy of the inherited environment. Never replace the environment wholesale.
    if env_overlay is not None or scrub_env_keys:
        base_env = dict(os.environ if inherited_env is None else inherited_env)
        overlay = {} if env_overlay is None else dict(env_overlay)
        kwargs["env"] = merge_process_environment(
            base_env,
            overlay,
            scrub_keys=scrub_env_keys,
        )

    try:
        completed = subprocess_run(**kwargs)
    except OSError:
        raise AgentRunError("No pude lanzar el proceso del executor: fallo al crear el proceso hijo.")

    return (
        int(getattr(completed, "returncode", 1)),
        _child_stream_bytes(getattr(completed, "stdout", None)),
        _child_stream_bytes(getattr(completed, "stderr", None)),
    )


def run_agent_process(
    *,
    executor: AgentExecutor,
    repo: str,
    workspace_root: Path,
    workdir: Path,
    targets: tuple[str, ...],
    prompt: str,
    shutil_which: Callable[[str], Optional[str]],
    subprocess_run: Callable[..., object] = subprocess.run,
    stream_writer: Callable[[str, bytes], None] | None = None,
    resource_id: Optional[str] = None,
    resource: Optional[AgentResource] = None,
    discover_free: Optional[DiscoverModelsFn] = None,
    discover_go: Optional[DiscoverModelsFn] = None,
    auth_evidence: object = None,
    inherited_env: Mapping[str, str] | None = None,
    model: Optional[str] = None,
    sandbox: Optional[str] = None,
) -> tuple[int, AgentRunMetadata]:
    started_at = datetime.now(timezone.utc).isoformat()
    workdir_resolved = str(workdir.resolve())
    workspace_resolved = str(workspace_root.resolve())
    contract_body = build_execution_contract(
        request=AgentRunRequest(
            executor=executor,
            repo=repo,
            workspace_root=workspace_resolved,
            workdir=workdir_resolved,
            targets=targets,
            user_prompt=prompt,
            contract_body="",
            model=model,
            sandbox=sandbox,
        )
    )
    request = AgentRunRequest(
        executor=executor,
        repo=repo,
        workspace_root=workspace_resolved,
        workdir=workdir_resolved,
        targets=targets,
        user_prompt=prompt,
        contract_body=contract_body,
        model=model,
        sandbox=sandbox,
    )

    try:
        if (model is not None or sandbox is not None) and executor.adapter != "codex":
            raise AgentRunError("Las opciones -m/--model y -s/--sandbox solo son validas con el executor codex.")
        adapter = resolve_adapter(executor.adapter)
        invocation = adapter.build_invocation(request)
    except ValueError as exc:
        raise AgentRunError(str(exc)) from exc

    if not executable_is_ready(executor.executable, shutil_which=shutil_which):
        raise AgentRunError(
            f"No pude lanzar el executor `{executor.executor_id}`: "
            f"el ejecutable no esta disponible."
        )

    env_overlay: dict[str, str] | None = None
    scrub_env_keys: frozenset[str] = frozenset()
    effective_resource_id = resource_id
    if resource is not None:
        effective_resource_id = resource.resource_id
        model_id = resolve_resource_model(
            resource,
            discover_free=discover_free,
            discover_go=discover_go,
            auth_evidence=auth_evidence,
        )
        built_overlay, scrub_env_keys = build_resource_process_overlay(
            resource,
            model_id=model_id,
        )
        # Local worker_profile returns an empty overlay: keep true env inheritance
        # (no env= kwarg) so operator-provided OPENCODE_CONFIG_CONTENT is preserved.
        if built_overlay or scrub_env_keys:
            env_overlay = built_overlay

    exit_code, stdout, stderr = execute_subprocess(
        invocation,
        cwd=workdir,
        subprocess_run=subprocess_run,
        env_overlay=env_overlay,
        scrub_env_keys=scrub_env_keys,
        inherited_env=inherited_env,
    )
    writer = stream_writer or _default_stream_writer
    if stdout:
        writer("stdout", stdout)
    if stderr:
        writer("stderr", stderr)

    finished_at = datetime.now(timezone.utc).isoformat()
    metadata = AgentRunMetadata(
        executor_id=executor.executor_id,
        repo=repo,
        workdir=str(workdir.resolve()),
        targets=targets,
        started_at=started_at,
        finished_at=finished_at,
        exit_code=exit_code,
        resource_id=effective_resource_id,
    )
    return exit_code, metadata


def _default_stream_writer(stream: str, payload: bytes) -> None:
    if stream == "stdout":
        target = getattr(sys.stdout, "buffer", None)
        if target is not None:
            target.write(payload)
            return
        sys.stdout.write(payload.decode("utf-8", errors="surrogateescape"))
        return
    target = getattr(sys.stderr, "buffer", None)
    if target is not None:
        target.write(payload)
        return
    sys.stderr.write(payload.decode("utf-8", errors="surrogateescape"))


def prepare_agent_run(
    *,
    executor_id: str,
    repo_raw: str,
    workdir_raw: str,
    prompt_raw: str,
    target_raws: Sequence[str],
    workspace_root: Path,
    workspace_config_file: Path,
    workspace_config: dict[str, object],
    root_repo: str,
    run_git: Callable[..., object] = subprocess.run,
) -> PreparedAgentRun:
    try:
        executors = load_agent_registry(workspace_config_file)
    except AgentRegistryError as exc:
        raise AgentRunError(exc.message) from exc

    executor, resource_id, resource = resolve_agent_selector(
        executor_id,
        executors=executors,
        workspace_config=workspace_config,
    )

    repos = workspace_config.get("repos")
    if not isinstance(repos, dict):
        raise AgentRunError("workspace.config.json debe definir `repos`.")

    repo = resolve_repo_id(repo_raw, repos=repos, root_repo=root_repo)
    repo_root_path = resolve_repo_root(
        repo,
        workspace_root=workspace_root,
        repos=repos,
        root_repo=root_repo,
    )
    workdir = validate_workdir(
        workdir_raw,
        workspace_root=workspace_root,
        repo_root_path=repo_root_path,
        run_git=run_git,
    )
    prompt = validate_prompt(prompt_raw)
    targets = normalize_targets(workdir, target_raws)
    return PreparedAgentRun(
        executor=executor,
        repo=repo,
        workdir=workdir,
        targets=targets,
        prompt=prompt,
        resource_id=resource_id,
        resource=resource,
    )
