from __future__ import annotations

import shutil
from typing import Callable


def command_stack_doctor(
    _,
    *,
    detect_compose_context: Callable[[], dict[str, object]],
    compose_control_file: Callable[[], object],
    compose_control_root: Callable[[], object],
    workspace_service: str,
    project_name: str,
) -> int:
    context = detect_compose_context()
    docker_ok = shutil.which("docker") is not None

    print(f"{project_name} stack doctor")
    print(f"- docker_cli: {'ok' if docker_ok else 'missing'}")
    print(f"- compose_file: {compose_control_file().resolve()}")
    print(f"- compose_root: {compose_control_root().resolve()}")
    print(f"- compose_project: {context['project']}")
    print(f"- compose_active: {'yes' if context['active'] else 'no'}")
    print(f"- workspace_service: {workspace_service}")
    return 0 if docker_ok else 1


def command_stack_ps(_, *, run_compose: Callable[[list[str], bool | None], int]) -> int:
    return run_compose(["ps"], None)


def command_stack_up(
    args,
    *,
    ensure_devcontainer_env: Callable[[], int],
    run_compose: Callable[[list[str], bool | None], int],
    services: list[str] | None = None,
) -> int:
    env_rc = ensure_devcontainer_env()
    if env_rc != 0:
        return env_rc
    command = ["up", "-d"]
    if args.build:
        command.append("--build")
    if services:
        command.extend(services)
    return run_compose(command, None)


def command_stack_down(args, *, run_compose: Callable[[list[str], bool | None], int]) -> int:
    command = ["down"]
    if args.volumes:
        command.append("-v")
    if args.rmi_local:
        command.extend(["--rmi", "local"])
    return run_compose(command, None)


def command_stack_build(args, *, run_compose: Callable[[list[str], bool | None], int]) -> int:
    command = ["build"]
    if args.no_cache:
        command.append("--no-cache")
    return run_compose(command, None)


def command_stack_logs(args, *, run_compose: Callable[[list[str], bool | None], int]) -> int:
    command = ["logs"]
    if args.follow:
        command.append("-f")
    if args.service:
        command.append(args.service)
    return run_compose(command, args.follow)


def command_stack_sh(
    args,
    *,
    run_compose: Callable[[list[str], bool | None], int],
    compose_exec_args: Callable[..., list[str]],
    workspace_service: str,
    workspace_path: str,
) -> int:
    service = args.service or workspace_service
    workdir = workspace_path if service == workspace_service else None
    return run_compose(
        compose_exec_args(service, interactive=True, workdir=workdir) + [args.shell],
        True,
    )


def command_stack_exec(
    args,
    *,
    normalize_passthrough: Callable[[list[str]], list[str]],
    run_compose: Callable[[list[str], bool | None], int],
    compose_exec_args: Callable[..., list[str]],
    workspace_service: str,
    workspace_path: str,
) -> int:
    command = normalize_passthrough(args.command)
    if not command:
        raise SystemExit("Debes indicar un comando despues del servicio. Ejemplo: `flow stack exec workspace -- ls -la`.")
    interactive = not args.no_tty
    workdir = workspace_path if args.service == workspace_service else None
    return run_compose(
        compose_exec_args(args.service, interactive=interactive, workdir=workdir) + command,
        interactive=interactive,
    )
