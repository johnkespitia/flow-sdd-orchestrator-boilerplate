from __future__ import annotations

from pathlib import Path

import pytest

from flowctl.tooling import capture_command, command_workspace_exec


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
