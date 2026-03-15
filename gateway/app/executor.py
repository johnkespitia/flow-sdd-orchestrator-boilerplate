from __future__ import annotations

import json
import subprocess
from typing import Any

from .config import Settings


def run_flow_command(settings: Settings, command: list[str]) -> dict[str, Any]:
    full_command = [settings.flow_bin, settings.flow_entrypoint, *command]
    result = subprocess.run(
        full_command,
        cwd=settings.workspace_root,
        capture_output=True,
        text=True,
        check=False,
    )

    parsed_output = None
    stdout = result.stdout.strip()
    if stdout:
        try:
            parsed_output = json.loads(stdout)
        except json.JSONDecodeError:
            parsed_output = None

    return {
        "command": full_command,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "parsed_output": parsed_output,
    }
