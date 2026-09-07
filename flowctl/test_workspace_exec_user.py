from __future__ import annotations

import importlib.machinery
import importlib.util
import re
from pathlib import Path

import pytest

from flowctl import stack
from flowctl.context import workspace_exec_user
from flowctl.stack_ops import command_stack_exec, command_stack_sh
from flowctl.tooling import capture_workspace_tool, command_repo_exec, run_workspace_tool

ROOT = Path(__file__).resolve().parents[1]
FLOW_PATH = ROOT / "flow"
ENTRYPOINT_PATH = ROOT / ".devcontainer" / "workspace-entrypoint.sh"
COMPOSE_PATH = ROOT / ".devcontainer" / "docker-compose.yml"


def test_compose_exec_args_with_user_emits_user_flag() -> None:
    args = stack.compose_exec_args("workspace", use_tty=False, workdir="/workspace", user="vscode")

    assert args == ["exec", "-T", "--user", "vscode", "-w", "/workspace", "workspace"]


def test_compose_exec_args_without_user_omits_user_flag() -> None:
    args = stack.compose_exec_args("api", use_tty=True, workdir="/workspace/projects/api")

    assert args == ["exec", "-w", "/workspace/projects/api", "api"]


def test_run_workspace_tool_passes_configured_workspace_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLOW_WORKSPACE_USER", "devuser")
    captured: list[dict[str, object]] = []

    def compose_exec_args(service, *, interactive=False, workdir=None, user=None):  # noqa: ANN001
        captured.append(
            {"service": service, "interactive": interactive, "workdir": workdir, "user": user}
        )
        return ["exec", service]

    rc = run_workspace_tool(
        ["python3", "./flow", "doctor"],
        run_compose=lambda args, interactive=None: 0,
        compose_exec_args=compose_exec_args,
        workspace_service="workspace",
        workspace_path="/workspace",
        workspace_exec_user=workspace_exec_user(),
    )

    assert rc == 0
    assert captured == [
        {
            "service": "workspace",
            "interactive": None,
            "workdir": "/workspace",
            "user": "devuser",
        }
    ]


def test_capture_workspace_tool_passes_default_workspace_user() -> None:
    captured: list[dict[str, object]] = []

    def compose_exec_args(service, *, interactive=False, workdir=None, user=None):  # noqa: ANN001
        captured.append(
            {"service": service, "interactive": interactive, "workdir": workdir, "user": user}
        )
        return ["exec", service]

    execution = capture_workspace_tool(
        ["tessl", "--help"],
        root=Path("/tmp"),
        running_inside_workspace=lambda: False,
        capture_command=lambda command, cwd: {"command": command, "cwd": str(cwd)},
        capture_compose=lambda args: {"command": args},
        compose_exec_args=compose_exec_args,
        workspace_service="workspace",
        workspace_path="/workspace",
        workspace_exec_user=workspace_exec_user(),
    )

    assert execution == {"command": ["exec", "workspace", "tessl", "--help"]}
    assert captured == [
        {
            "service": "workspace",
            "interactive": False,
            "workdir": "/workspace",
            "user": "vscode",
        }
    ]


def test_command_repo_exec_does_not_force_workspace_user_from_host() -> None:
    repo_dir = Path("/tmp/projects/api")
    captured: list[dict[str, object]] = []

    def compose_exec_args(service_name, interactive=False, workdir=None, user=None):  # noqa: ANN001
        captured.append(
            {
                "service": service_name,
                "interactive": interactive,
                "workdir": workdir,
                "user": user,
            }
        )
        return ["exec", service_name, workdir or ""]

    rc = command_repo_exec(
        type("Args", (), {"repo": "api", "workdir": "", "command": ["--", "vendor/bin/phpunit"]})(),
        normalize_passthrough=lambda args: args[1:] if args and args[0] == "--" else args,
        repo_root=lambda repo: repo_dir,
        repo_compose_service=lambda repo: "php-api",
        workspace_service="workspace",
        running_inside_workspace=lambda: False,
        runtime_path=lambda path: path,
        repo_container_workdir=lambda path: "/workspace/projects/api",
        run_local_tool_at_path=lambda tool_args, cwd: 0,
        run_compose=lambda args, interactive=None: 0,
        compose_exec_args=compose_exec_args,
    )

    assert rc == 0
    assert captured == [
        {
            "service": "php-api",
            "interactive": False,
            "workdir": "/workspace/projects/api",
            "user": None,
        }
    ]


def test_command_repo_exec_uses_workspace_user_for_workspace_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FLOW_WORKSPACE_USER", "devuser")
    repo_dir = Path("/tmp/projects/root-repo")
    captured: list[dict[str, object]] = []

    def compose_exec_args(service_name, interactive=False, workdir=None, user=None):  # noqa: ANN001
        captured.append(
            {
                "service": service_name,
                "interactive": interactive,
                "workdir": workdir,
                "user": user,
            }
        )
        return ["exec", service_name, workdir or ""]

    rc = command_repo_exec(
        type(
            "Args",
            (),
            {"repo": "sdd-workspace-boilerplate", "workdir": "", "command": ["--", "pytest"]},
        )(),
        normalize_passthrough=lambda args: args[1:] if args and args[0] == "--" else args,
        repo_root=lambda repo: repo_dir,
        repo_compose_service=lambda repo: "workspace",
        workspace_service="workspace",
        workspace_exec_user=workspace_exec_user(),
        running_inside_workspace=lambda: False,
        runtime_path=lambda path: path,
        repo_container_workdir=lambda path: "/workspace",
        run_local_tool_at_path=lambda tool_args, cwd: 0,
        run_compose=lambda args, interactive=None: 0,
        compose_exec_args=compose_exec_args,
    )

    assert rc == 0
    assert captured == [
        {
            "service": "workspace",
            "interactive": False,
            "workdir": "/workspace",
            "user": "devuser",
        }
    ]


def test_wrap_repo_command_for_service_uses_workspace_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLOW_WORKSPACE_USER", "devuser")
    flow_spec = importlib.util.spec_from_loader(
        "flow_cli_wrap_repo",
        importlib.machinery.SourceFileLoader("flow_cli_wrap_repo", str(FLOW_PATH)),
    )
    flow_module = importlib.util.module_from_spec(flow_spec)
    assert flow_spec.loader is not None
    flow_spec.loader.exec_module(flow_module)

    captured: list[dict[str, object]] = []

    def compose_exec_args(service_name, interactive=False, workdir=None, user=None):  # noqa: ANN001
        captured.append(
            {
                "service": service_name,
                "interactive": interactive,
                "workdir": workdir,
                "user": user,
            }
        )
        return ["exec", "-w", workdir or "", service_name]

    original_compose_exec_args = flow_module.compose_exec_args
    original_compose_base_command = flow_module.compose_base_command
    original_repo_container_workdir = flow_module.repo_container_workdir
    try:
        flow_module.compose_exec_args = compose_exec_args
        flow_module.compose_base_command = lambda: ["compose"]
        flow_module.repo_container_workdir = lambda path: "/workspace"
        wrapped = flow_module.wrap_repo_command_for_service(
            "sdd-workspace-boilerplate",
            Path("/tmp/root"),
            ["pytest"],
        )
    finally:
        flow_module.compose_exec_args = original_compose_exec_args
        flow_module.compose_base_command = original_compose_base_command
        flow_module.repo_container_workdir = original_repo_container_workdir

    assert wrapped == ["compose", "exec", "-w", "/workspace", "workspace", "pytest"]
    assert captured == [
        {
            "service": "workspace",
            "interactive": False,
            "workdir": "/workspace",
            "user": "devuser",
        }
    ]


def test_wrap_repo_command_for_service_does_not_force_user_for_other_services(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FLOW_WORKSPACE_USER", "devuser")
    flow_spec = importlib.util.spec_from_loader(
        "flow_cli_wrap_repo_other",
        importlib.machinery.SourceFileLoader("flow_cli_wrap_repo_other", str(FLOW_PATH)),
    )
    flow_module = importlib.util.module_from_spec(flow_spec)
    assert flow_spec.loader is not None
    flow_spec.loader.exec_module(flow_module)

    captured: list[dict[str, object]] = []

    def compose_exec_args(service_name, interactive=False, workdir=None, user=None):  # noqa: ANN001
        captured.append(
            {
                "service": service_name,
                "interactive": interactive,
                "workdir": workdir,
                "user": user,
            }
        )
        return ["exec", "-w", workdir or "", service_name]

    original_compose_exec_args = flow_module.compose_exec_args
    original_compose_base_command = flow_module.compose_base_command
    original_repo_compose_service = flow_module.repo_compose_service
    original_repo_container_workdir = flow_module.repo_container_workdir
    try:
        flow_module.compose_exec_args = compose_exec_args
        flow_module.compose_base_command = lambda: ["compose"]
        flow_module.repo_compose_service = lambda repo: "php-api"
        flow_module.repo_container_workdir = lambda path: "/workspace/projects/api"
        wrapped = flow_module.wrap_repo_command_for_service(
            "api",
            Path("/tmp/projects/api"),
            ["vendor/bin/phpunit"],
        )
    finally:
        flow_module.compose_exec_args = original_compose_exec_args
        flow_module.compose_base_command = original_compose_base_command
        flow_module.repo_compose_service = original_repo_compose_service
        flow_module.repo_container_workdir = original_repo_container_workdir

    assert wrapped == [
        "compose",
        "exec",
        "-w",
        "/workspace/projects/api",
        "php-api",
        "vendor/bin/phpunit",
    ]
    assert captured == [
        {
            "service": "php-api",
            "interactive": False,
            "workdir": "/workspace/projects/api",
            "user": None,
        }
    ]


def test_workspace_entrypoint_drops_to_development_user() -> None:
    entrypoint = ENTRYPOINT_PATH.read_text(encoding="utf-8")

    assert 'workspace_user="${FLOW_WORKSPACE_USER:-vscode}"' in entrypoint
    assert "prepare_runtime_user_dirs()" in entrypoint
    assert 'workspace_home="$(getent passwd "$workspace_user" | cut -d: -f6 || true)"' in entrypoint
    assert '"$workspace_home/.local"' in entrypoint
    assert '"$workspace_home/.local/share"' in entrypoint
    assert '"$workspace_home/.local/share/tessl"' in entrypoint
    assert '"$workspace_home/.local/share/pnpm/store"' in entrypoint
    assert '"$workspace_home/.config"' in entrypoint
    assert '"$workspace_home/.cache"' in entrypoint
    assert 'chown "$target_uid:$target_gid" "${runtime_dirs[@]}"' in entrypoint
    assert "groupadd" in entrypoint
    assert "usermod" in entrypoint
    assert 'target_uid="$(id -u "$workspace_user")"' in entrypoint
    assert 'target_gid="$(id -g "$workspace_user")"' in entrypoint
    assert re.search(
        r'setpriv\s+--reuid="\$target_uid"\s+--regid="\$target_gid"\s+--init-groups\s+--',
        entrypoint,
    )
    assert "runuser" not in entrypoint


def test_workspace_and_gateway_compose_use_non_root_runtime_contract() -> None:
    compose = COMPOSE_PATH.read_text(encoding="utf-8")

    workspace_block = compose.split("  gateway:")[0]
    gateway_block = compose.split("  gateway:")[1].split("\n\n")[0]

    assert "workspace:" in workspace_block
    assert "user: root" in workspace_block
    assert 'entrypoint: ["/usr/local/share/flow/workspace-entrypoint.sh"]' in workspace_block

    assert "user: root" in gateway_block
    assert 'entrypoint: ["/usr/local/share/flow/workspace-entrypoint.sh"]' in gateway_block


def test_workspace_exec_user_defaults_to_vscode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FLOW_WORKSPACE_USER", raising=False)
    assert workspace_exec_user() == "vscode"


def test_workspace_exec_user_reads_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLOW_WORKSPACE_USER", "custom")
    assert workspace_exec_user() == "custom"


def test_command_stack_exec_uses_workspace_user_for_workspace_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FLOW_WORKSPACE_USER", "devuser")
    captured: list[dict[str, object]] = []

    def compose_exec_args(service, *, interactive=False, workdir=None, user=None):  # noqa: ANN001
        captured.append(
            {"service": service, "interactive": interactive, "workdir": workdir, "user": user}
        )
        return ["exec", service]

    rc = command_stack_exec(
        type("Args", (), {"service": "workspace", "no_tty": True, "command": ["--", "id"]})(),
        normalize_passthrough=lambda args: args[1:] if args and args[0] == "--" else args,
        run_compose=lambda args, interactive=None: 0,
        compose_exec_args=compose_exec_args,
        workspace_service="workspace",
        workspace_path="/workspace",
        workspace_exec_user=workspace_exec_user(),
    )

    assert rc == 0
    assert captured == [
        {
            "service": "workspace",
            "interactive": False,
            "workdir": "/workspace",
            "user": "devuser",
        }
    ]


def test_command_stack_sh_uses_workspace_user_for_workspace_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FLOW_WORKSPACE_USER", "devuser")
    captured: list[dict[str, object]] = []

    def compose_exec_args(service, *, interactive=False, workdir=None, user=None):  # noqa: ANN001
        captured.append(
            {"service": service, "interactive": interactive, "workdir": workdir, "user": user}
        )
        return ["exec", service]

    rc = command_stack_sh(
        type("Args", (), {"service": None, "shell": "sh"})(),
        run_compose=lambda args, interactive=None: 0,
        compose_exec_args=compose_exec_args,
        workspace_service="workspace",
        workspace_path="/workspace",
        workspace_exec_user=workspace_exec_user(),
    )

    assert rc == 0
    assert captured == [
        {
            "service": "workspace",
            "interactive": True,
            "workdir": "/workspace",
            "user": "devuser",
        }
    ]


def test_command_stack_exec_does_not_force_user_for_other_services() -> None:
    captured: list[dict[str, object]] = []

    def compose_exec_args(service, *, interactive=False, workdir=None, user=None):  # noqa: ANN001
        captured.append(
            {"service": service, "interactive": interactive, "workdir": workdir, "user": user}
        )
        return ["exec", service]

    rc = command_stack_exec(
        type("Args", (), {"service": "gateway", "no_tty": True, "command": ["id"]})(),
        normalize_passthrough=lambda args: args,
        run_compose=lambda args, interactive=None: 0,
        compose_exec_args=compose_exec_args,
        workspace_service="workspace",
        workspace_path="/workspace",
        workspace_exec_user=workspace_exec_user(),
    )

    assert rc == 0
    assert captured == [
        {
            "service": "gateway",
            "interactive": False,
            "workdir": None,
            "user": None,
        }
    ]


def test_command_stack_sh_does_not_force_user_for_other_services() -> None:
    captured: list[dict[str, object]] = []

    def compose_exec_args(service, *, interactive=False, workdir=None, user=None):  # noqa: ANN001
        captured.append(
            {"service": service, "interactive": interactive, "workdir": workdir, "user": user}
        )
        return ["exec", service]

    rc = command_stack_sh(
        type("Args", (), {"service": "gateway", "shell": "sh"})(),
        run_compose=lambda args, interactive=None: 0,
        compose_exec_args=compose_exec_args,
        workspace_service="workspace",
        workspace_path="/workspace",
        workspace_exec_user=workspace_exec_user(),
    )

    assert rc == 0
    assert captured == [
        {
            "service": "gateway",
            "interactive": True,
            "workdir": None,
            "user": None,
        }
    ]
