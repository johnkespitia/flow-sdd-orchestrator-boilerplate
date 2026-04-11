from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from flowctl.memory_ops import (
    command_memory_doctor,
    command_memory_export,
    command_memory_save,
    command_memory_search,
    command_memory_smoke,
    command_memory_stats,
    parse_search_stdout,
)


def _json_dumps(payload: object) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True)


class MemoryOpsTests(unittest.TestCase):
    def test_parse_search_stdout_returns_structured_items(self) -> None:
        stdout = """Found 1 memories:

[1] #42 (manual) — SoftOS memory smoke
    TYPE: outcome
    Project: softos-sdd-orchestrator
    Area: memory-smoke
    2026-04-11 13:54:31 | scope: project
"""

        items = parse_search_stdout(stdout)

        self.assertEqual(1, len(items))
        self.assertEqual("42", items[0]["id"])
        self.assertEqual("manual", items[0]["kind"])
        self.assertEqual("SoftOS memory smoke", items[0]["title"])
        self.assertEqual("project", items[0]["scope"])
        self.assertEqual("2026-04-11 13:54:31", items[0]["created_at"])
        self.assertIn("TYPE: outcome", items[0]["body"])

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

    def test_smoke_runs_version_stats_context_and_search(self) -> None:
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
                ["/usr/local/bin/engram", "search", root.name],
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

    def test_stats_runs_project_scoped_engram_stats(self) -> None:
        commands: list[list[str]] = []

        def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="stats\n", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            rc = command_memory_stats(
                Namespace(json=True),
                root=Path(tmp),
                workspace_config={},
                json_dumps=_json_dumps,
                which=lambda _name: "/usr/local/bin/engram",
                run_command=fake_run,
            )

        self.assertEqual(0, rc)
        self.assertEqual([["/usr/local/bin/engram", "stats"]], commands)

    def test_search_runs_project_scoped_engram_search(self) -> None:
        commands: list[list[str]] = []

        def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="found\n", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            rc = command_memory_search(
                Namespace(json=True, query="SoftOS"),
                root=Path(tmp),
                workspace_config={},
                json_dumps=_json_dumps,
                which=lambda _name: "/usr/local/bin/engram",
                run_command=fake_run,
            )

        self.assertEqual(0, rc)
        self.assertEqual([["/usr/local/bin/engram", "search", "SoftOS"]], commands)

    def test_search_json_includes_structured_items(self) -> None:
        stdout = """Found 1 memories:

[1] #7 (manual) — Wrapper
    Body line
    2026-04-11 14:25:54 | scope: project
"""

        def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            rc = command_memory_search(
                Namespace(json=True, query="Wrapper"),
                root=Path(tmp),
                workspace_config={},
                json_dumps=_json_dumps,
                which=lambda _name: "/usr/local/bin/engram",
                run_command=fake_run,
            )

        self.assertEqual(0, rc)

    def test_export_runs_native_engram_export(self) -> None:
        commands: list[list[str]] = []

        def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            Path(command[-1]).write_text(json.dumps({"observations": [{"id": 1}]}) + "\n", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="exported\n", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "memory-export.json"
            rc = command_memory_export(
                Namespace(json=True, output=str(output)),
                root=Path(tmp),
                workspace_config={},
                json_dumps=_json_dumps,
                which=lambda _name: "/usr/local/bin/engram",
                run_command=fake_run,
            )

        self.assertEqual(0, rc)
        self.assertEqual("/usr/local/bin/engram", commands[0][0])
        self.assertEqual("export", commands[0][1])

    def test_save_runs_project_scoped_engram_save_with_body(self) -> None:
        commands: list[list[str]] = []

        def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="saved\n", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            rc = command_memory_save(
                Namespace(json=True, title="Outcome", body="TYPE: outcome", body_file=None),
                root=Path(tmp),
                workspace_config={},
                json_dumps=_json_dumps,
                which=lambda _name: "/usr/local/bin/engram",
                run_command=fake_run,
            )

        self.assertEqual(0, rc)
        self.assertEqual([["/usr/local/bin/engram", "save", "Outcome", "TYPE: outcome"]], commands)

    def test_save_reads_body_file(self) -> None:
        commands: list[list[str]] = []

        def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="saved\n", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            body_path = root / "memory.txt"
            body_path.write_text("TYPE: decision\n", encoding="utf-8")
            rc = command_memory_save(
                Namespace(json=True, title="Decision", body=None, body_file=str(body_path)),
                root=root,
                workspace_config={},
                json_dumps=_json_dumps,
                which=lambda _name: "/usr/local/bin/engram",
                run_command=fake_run,
            )

        self.assertEqual(0, rc)
        self.assertEqual([["/usr/local/bin/engram", "save", "Decision", "TYPE: decision\n"]], commands)


if __name__ == "__main__":
    unittest.main()
