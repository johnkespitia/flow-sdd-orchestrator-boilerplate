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
    command_memory_backup,
    command_memory_import,
    command_memory_prune,
    command_memory_save,
    command_memory_search,
    command_memory_smoke,
    command_memory_stats,
    memory_execution_enabled,
    parse_search_stdout,
    save_release_outcome,
    write_plan_recall_report,
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

    def test_backup_writes_under_memory_backups(self) -> None:
        commands: list[list[str]] = []

        def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            Path(command[-1]).write_text(json.dumps({"observations": []}) + "\n", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="exported\n", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rc = command_memory_backup(
                Namespace(json=True),
                root=root,
                workspace_config={},
                json_dumps=_json_dumps,
                which=lambda _name: "/usr/local/bin/engram",
                run_command=fake_run,
            )

        self.assertEqual(0, rc)
        self.assertIn(".flow/memory/backups", commands[0][-1])

    def test_import_dry_run_validates_export_without_running_engram(self) -> None:
        commands: list[list[str]] = []

        def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="imported\n", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            export = root / "export.json"
            export.write_text(json.dumps({"observations": [{"id": 1, "title": "Safe", "content": "Body"}]}), encoding="utf-8")
            rc = command_memory_import(
                Namespace(json=True, file=str(export), confirm=False),
                root=root,
                workspace_config={},
                json_dumps=_json_dumps,
                which=lambda _name: "/usr/local/bin/engram",
                run_command=fake_run,
            )

        self.assertEqual(0, rc)
        self.assertEqual([], commands)

    def test_import_confirm_runs_native_engram_import(self) -> None:
        commands: list[list[str]] = []

        def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="imported\n", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            export = root / "export.json"
            export.write_text(json.dumps({"observations": []}), encoding="utf-8")
            rc = command_memory_import(
                Namespace(json=True, file=str(export), confirm=True),
                root=root,
                workspace_config={},
                json_dumps=_json_dumps,
                which=lambda _name: "/usr/local/bin/engram",
                run_command=fake_run,
            )

        self.assertEqual(0, rc)
        self.assertEqual("import", commands[0][1])

    def test_import_blocks_potential_secret_like_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            export = root / "export.json"
            export.write_text(
                json.dumps({"observations": [{"id": 1, "title": "Bad", "content": "token=abc"}]}),
                encoding="utf-8",
            )
            rc = command_memory_import(
                Namespace(json=True, file=str(export), confirm=True),
                root=root,
                workspace_config={},
                json_dumps=_json_dumps,
                which=lambda _name: "/usr/local/bin/engram",
            )

        self.assertEqual(1, rc)

    def test_prune_generates_advisory_report(self) -> None:
        commands: list[list[str]] = []

        def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            Path(command[-1]).write_text(
                json.dumps(
                    {
                        "observations": [
                            {
                                "id": 1,
                                "title": "Old smoke",
                                "content": "memory smoke",
                                "scope": "project",
                                "created_at": "2020-01-01T00:00:00+00:00",
                                "updated_at": "2020-01-01T00:00:00+00:00",
                            },
                            {
                                "id": 2,
                                "title": "Keep",
                                "content": "recent",
                                "scope": "project",
                                "created_at": "2026-01-01T00:00:00+00:00",
                                "updated_at": "2026-01-01T00:00:00+00:00",
                            },
                        ]
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 0, stdout="exported\n", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "prune-report.json"
            rc = command_memory_prune(
                Namespace(json=True, query="smoke", older_than_days=90, keep_latest=1, output=str(output)),
                root=root,
                workspace_config={},
                json_dumps=_json_dumps,
                which=lambda _name: "/usr/local/bin/engram",
                run_command=fake_run,
            )
            report = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(0, rc)
        self.assertEqual("export", commands[0][1])
        self.assertFalse(report["destructive"])
        self.assertGreaterEqual(report["candidate_count"], 1)

    def test_memory_execution_gates_are_off_by_default(self) -> None:
        args = Namespace(memory_recall=None, memory_save_outcome=None)

        self.assertFalse(memory_execution_enabled(args, workspace_config={}, arg_name="memory_recall", config_name="recall_before_plan"))
        self.assertFalse(
            memory_execution_enabled(
                args,
                workspace_config={},
                arg_name="memory_save_outcome",
                config_name="save_after_release_publish",
            )
        )

    def test_memory_execution_gates_can_use_flags_or_config(self) -> None:
        cfg = {"memory": {"execution": {"recall_before_plan": True, "save_after_release_publish": True}}}

        self.assertTrue(memory_execution_enabled(Namespace(memory_recall=None), workspace_config=cfg, arg_name="memory_recall", config_name="recall_before_plan"))
        self.assertTrue(memory_execution_enabled(Namespace(memory_recall=True), workspace_config={}, arg_name="memory_recall", config_name="recall_before_plan"))
        self.assertFalse(memory_execution_enabled(Namespace(memory_recall=False), workspace_config=cfg, arg_name="memory_recall", config_name="recall_before_plan"))
        self.assertTrue(
            memory_execution_enabled(
                Namespace(memory_save_outcome=None),
                workspace_config=cfg,
                arg_name="memory_save_outcome",
                config_name="save_after_release_publish",
            )
        )
        self.assertFalse(
            memory_execution_enabled(
                Namespace(memory_save_outcome=False),
                workspace_config=cfg,
                arg_name="memory_save_outcome",
                config_name="save_after_release_publish",
            )
        )

    def test_write_plan_recall_report_runs_search_and_writes_report(self) -> None:
        commands: list[list[str]] = []
        stdout = """Found 1 memories:

[1] #7 (manual) — Planning gotcha
    Use explicit gates
    2026-04-11 14:25:54 | scope: project
"""

        def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = write_plan_recall_report(
                root=root,
                workspace_config={},
                slug="feature-spec",
                spec_path=root / "specs" / "features" / "feature-spec.spec.md",
                json_dumps=_json_dumps,
                which=lambda _name: "/usr/local/bin/engram",
                run_command=fake_run,
            )
            output = Path(str(payload["report"]))
            self.assertTrue(output.exists())
            self.assertEqual(1, json.loads(output.read_text(encoding="utf-8"))["count"])

        self.assertTrue(payload["ok"])
        self.assertEqual([["/usr/local/bin/engram", "search", "feature-spec"]], commands)

    def test_save_release_outcome_runs_engram_save_with_safe_command(self) -> None:
        commands: list[list[str]] = []

        def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="saved\n", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            payload = save_release_outcome(
                root=Path(tmp),
                workspace_config={},
                version="v0.9.6",
                json_dumps=_json_dumps,
                which=lambda _name: "/usr/local/bin/engram",
                run_command=fake_run,
            )

        self.assertTrue(payload["ok"])
        self.assertEqual("save", commands[0][1])
        self.assertIn("SoftOS release publish outcome v0.9.6", commands[0][2])
        self.assertIn("TYPE: outcome", commands[0][3])
        self.assertEqual("/usr/local/bin/engram save 'SoftOS release publish outcome v0.9.6' <body>", payload["step"]["command"])

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
