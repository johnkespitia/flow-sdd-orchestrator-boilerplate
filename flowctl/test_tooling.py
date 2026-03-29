from __future__ import annotations

from pathlib import Path

from flowctl.tooling import capture_command


def test_capture_command_reports_missing_executable_instead_of_crashing() -> None:
    execution = capture_command(["definitely-missing-softos-binary-xyz"], Path.cwd())

    assert execution["command"] == ["definitely-missing-softos-binary-xyz"]
    assert execution["cwd"] == str(Path.cwd())
    assert execution["returncode"] == 127
    assert "No encontre el ejecutable `definitely-missing-softos-binary-xyz`" in str(execution["output_tail"])
