from __future__ import annotations

from pathlib import Path

import pytest

from flowctl.tooling import capture_command, command_repo_exec, command_workspace_exec


def test_capture_command_reports_missing_executable_instead_of_crashing() -> None:
    execution = capture_command(["definitely-missing-softos-binary-xyz"], Path.cwd())

    assert execution["command"] == ["definitely-missing-softos-binary-xyz"]
    assert execution["cwd"] == str(Path.cwd())
    assert execution["returncode"] == 127
    assert "No encontre el ejecutable `definitely-missing-softos-binary-xyz`" in str(execution["output_tail"])


def test_command_workspace_exec_runs_locally_inside_workspace() -> None:
    calls: list[tuple[str, list[str]]] = []

    rc = command_workspace_exec(
        type("Args", (), {"command": ["--", "python3", "./flow", "doctor"]})(),
        normalize_passthrough=lambda args: args[1:] if args and args[0] == "--" else args,
        running_inside_workspace=lambda: True,
        run_local_tool=lambda tool_args: calls.append(("local", tool_args)) or 0,
        run_workspace_tool=lambda tool_args: calls.append(("workspace", tool_args)) or 0,
    )

    assert rc == 0
    assert calls == [("local", ["python3", "./flow", "doctor"])]


def test_command_workspace_exec_delegates_from_host() -> None:
    calls: list[tuple[str, list[str]]] = []

    rc = command_workspace_exec(
        type("Args", (), {"command": ["--", "tessl", "--help"]})(),
        normalize_passthrough=lambda args: args[1:] if args and args[0] == "--" else args,
        running_inside_workspace=lambda: False,
        run_local_tool=lambda tool_args: calls.append(("local", tool_args)) or 0,
        run_workspace_tool=lambda tool_args: calls.append(("workspace", tool_args)) or 0,
    )

    assert rc == 0
    assert calls == [("workspace", ["tessl", "--help"])]


def test_command_workspace_exec_requires_command() -> None:
    with pytest.raises(SystemExit, match="Debes indicar un comando despues de `--`"):
        command_workspace_exec(
            type("Args", (), {"command": []})(),
            normalize_passthrough=lambda args: args,
            running_inside_workspace=lambda: False,
            run_local_tool=lambda tool_args: 0,
            run_workspace_tool=lambda tool_args: 0,
        )


def test_command_repo_exec_runs_in_repo_path_inside_workspace(tmp_path: Path) -> None:
    repo_dir = tmp_path / "projects" / "api"
    repo_dir.mkdir(parents=True, exist_ok=True)
    calls: list[tuple[str, list[str], Path | None]] = []

    rc = command_repo_exec(
        type("Args", (), {"repo": "api", "command": ["--", "vendor/bin/phpunit"]})(),
        normalize_passthrough=lambda args: args[1:] if args and args[0] == "--" else args,
        repo_root=lambda repo: repo_dir,
        repo_compose_service=lambda repo: "api",
        workspace_service="workspace",
        running_inside_workspace=lambda: True,
        runtime_path=lambda path: path,
        repo_container_workdir=lambda path: "/workspace/projects/api",
        run_local_tool_at_path=lambda tool_args, cwd: calls.append(("local", tool_args, cwd)) or 0,
        run_compose=lambda args, interactive=None: calls.append(("compose", args, None)) or 0,
        compose_exec_args=lambda service_name, interactive=False, workdir=None: ["exec", service_name, workdir or ""],
    )

    assert rc == 0
    assert calls == [("local", ["vendor/bin/phpunit"], repo_dir)]


def test_command_repo_exec_uses_repo_service_from_host() -> None:
    repo_dir = Path("/tmp/projects/api")
    calls: list[tuple[str, list[str], Path | None]] = []

    rc = command_repo_exec(
        type("Args", (), {"repo": "api", "command": ["--", "vendor/bin/phpunit"]})(),
        normalize_passthrough=lambda args: args[1:] if args and args[0] == "--" else args,
        repo_root=lambda repo: repo_dir,
        repo_compose_service=lambda repo: "php-api",
        workspace_service="workspace",
        running_inside_workspace=lambda: False,
        runtime_path=lambda path: path,
        repo_container_workdir=lambda path: "/workspace/projects/api",
        run_local_tool_at_path=lambda tool_args, cwd: calls.append(("local", tool_args, cwd)) or 0,
        run_compose=lambda args, interactive=None: calls.append(("compose", args, None)) or 0,
        compose_exec_args=lambda service_name, interactive=False, workdir=None: ["exec", service_name, workdir or ""],
    )

    assert rc == 0
    assert calls == [("compose", ["exec", "php-api", "/workspace/projects/api", "vendor/bin/phpunit"], None)]
