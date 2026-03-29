from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Callable, Optional


def capture_command(command: list[str], cwd: Path) -> dict[str, object]:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        executable = command[0] if command else "<empty>"
        return {
            "command": command,
            "cwd": str(cwd),
            "returncode": 127,
            "output_tail": f"No encontre el ejecutable `{executable}`: {exc}",
        }
    combined = (result.stdout + "\n" + result.stderr).strip()
    tail = "\n".join(combined.splitlines()[-40:]) if combined else ""
    return {
        "command": command,
        "cwd": str(cwd),
        "returncode": result.returncode,
        "output_tail": tail,
    }


def normalize_passthrough(args: list[str]) -> list[str]:
    if args and args[0] == "--":
        return args[1:]
    return args


def run_workspace_tool(
    tool_args: list[str],
    *,
    run_compose: Callable[[list[str], Optional[bool]], int],
    compose_exec_args: Callable[..., list[str]],
    workspace_service: str,
    workspace_path: str,
    interactive: Optional[bool] = None,
    workdir: Optional[str] = None,
) -> int:
    return run_compose(
        compose_exec_args(workspace_service, interactive=interactive, workdir=workdir or workspace_path) + tool_args,
        interactive,
    )


def capture_workspace_tool(
    tool_args: list[str],
    *,
    root: Path,
    running_inside_workspace: Callable[[], bool],
    capture_command: Callable[[list[str], Path], dict[str, object]],
    capture_compose: Callable[[list[str]], dict[str, object]],
    compose_exec_args: Callable[..., list[str]],
    workspace_service: str,
    workspace_path: str,
) -> dict[str, object]:
    if running_inside_workspace():
        return capture_command(tool_args, root)

    return capture_compose(
        compose_exec_args(workspace_service, interactive=False, workdir=workspace_path) + tool_args
    )


def run_local_tool(tool_args: list[str], *, root: Path) -> int:
    try:
        return subprocess.run(tool_args, cwd=root, check=False).returncode
    except FileNotFoundError as exc:
        raise SystemExit(f"No encontre el ejecutable `{tool_args[0]}`.") from exc


def bmad_command_prefix(
    *,
    env_first: Callable[..., Optional[str]],
    workspace_executable_available: Callable[[str], bool],
) -> list[str]:
    explicit = env_first("FLOW_BMAD_COMMAND", "PLG_BMAD_COMMAND")
    if explicit is not None:
        command_prefix = shlex.split(explicit)
        if not command_prefix:
            raise SystemExit("`FLOW_BMAD_COMMAND`/`PLG_BMAD_COMMAND` esta vacio; configura el comando BMAD primero.")
        return command_prefix

    for candidate in (["bmad"], ["bmad-method"], ["npx", "bmad-method"]):
        if workspace_executable_available(candidate[0]):
            return candidate

    raise SystemExit(
        "No encontre un runtime BMAD en el workspace. "
        "Rebuild del devcontainer para instalar `bmad-method`, o ajusta `FLOW_BMAD_COMMAND`."
    )


def command_tessl(
    args,
    *,
    normalize_passthrough: Callable[[list[str]], list[str]],
    running_inside_workspace: Callable[[], bool],
    run_local_tool: Callable[[list[str]], int],
    run_workspace_tool: Callable[[list[str]], int],
) -> int:
    passthrough = normalize_passthrough(args.args) or ["--help"]
    if running_inside_workspace():
        return run_local_tool(["tessl", *passthrough])
    return run_workspace_tool(["tessl", *passthrough])


def command_bmad(
    args,
    *,
    bmad_command_prefix: Callable[[], list[str]],
    normalize_passthrough: Callable[[list[str]], list[str]],
    running_inside_workspace: Callable[[], bool],
    run_local_tool: Callable[[list[str]], int],
    run_workspace_tool: Callable[[list[str]], int],
) -> int:
    command_prefix = bmad_command_prefix()
    passthrough = normalize_passthrough(args.args) or ["--help"]
    full_command = [*command_prefix, *passthrough]

    if running_inside_workspace():
        return run_local_tool(full_command)

    return run_workspace_tool(full_command)
