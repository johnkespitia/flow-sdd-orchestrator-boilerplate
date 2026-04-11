from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from flowctl.memory_ops import command_memory_doctor, command_memory_smoke


def _json_dumps(payload: object) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True)


class MemoryOpsTests(unittest.TestCase):
    def test_doctor_is_non_blocking_when_engram_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.dict(os.environ, {}, clear=True):
                rc = command_memory_doctor(
                    Namespace(json=False),
                    root=root,
                    workspace_config={},
                    json_dumps=_json_dumps,
                    which=lambda _name: None,
                )

            self.assertEqual(0, rc)
            self.assertTrue((root / ".flow" / "memory" / "engram").is_dir())

    def test_doctor_uses_project_scoped_environment(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append({"command": command, "env": kwargs.get("env")})
            return subprocess.CompletedProcess(command, 0, stdout="engram v1.11.0\n", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.dict(os.environ, {"ENGRAM_PROJECT": "project-a"}, clear=True):
                rc = command_memory_doctor(
                    Namespace(json=True),
                    root=root,
                    workspace_config={},
                    json_dumps=_json_dumps,
                    which=lambda _name: "/usr/local/bin/engram",
                    run_command=fake_run,
                )

        self.assertEqual(0, rc)
        self.assertEqual(["/usr/local/bin/engram", "version"], calls[0]["command"])
        env = calls[0]["env"]
        self.assertIsInstance(env, dict)
        self.assertEqual("project-a", env["ENGRAM_PROJECT"])
        self.assertTrue(str(env["ENGRAM_DATA_DIR"]).endswith(".flow/memory/engram"))

    def test_smoke_runs_version_stats_and_context(self) -> None:
        commands: list[list[str]] = []

        def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rc = command_memory_smoke(
                Namespace(json=True, save=False),
                root=root,
                workspace_config={},
                json_dumps=_json_dumps,
                which=lambda _name: "/usr/local/bin/engram",
                run_command=fake_run,
            )

        self.assertEqual(0, rc)
        self.assertEqual(
            [
                ["/usr/local/bin/engram", "version"],
                ["/usr/local/bin/engram", "stats"],
                ["/usr/local/bin/engram", "context", root.name],
            ],
            commands,
        )

    def test_smoke_save_writes_structured_memory(self) -> None:
        commands: list[list[str]] = []

        def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rc = command_memory_smoke(
                Namespace(json=True, save=True),
                root=root,
                workspace_config={},
                json_dumps=_json_dumps,
                which=lambda _name: "/usr/local/bin/engram",
                run_command=fake_run,
            )

        self.assertEqual(0, rc)
        self.assertEqual("/usr/local/bin/engram", commands[-1][0])
        self.assertEqual("save", commands[-1][1])
        self.assertEqual("SoftOS memory smoke", commands[-1][2])
        self.assertIn("TYPE: outcome", commands[-1][3])


if __name__ == "__main__":
    unittest.main()
