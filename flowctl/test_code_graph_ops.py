from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path

from flowctl.code_graph_ops import (
    command_code_graph_doctor,
    command_code_graph_refresh,
    inspect_repo,
    inspect_repos,
    refresh_repo,
)


def _json_dumps(payload: object) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True)


def _config(repos: dict[str, dict[str, object]]) -> dict[str, object]:
    return {
        "project": {"root_repo": "root"},
        "repos": repos,
        "code_graph": {
            "provider": "graphify",
            "version": "0.9.56",
            "output_dir": "graphify-out",
            "mode": "code-only",
            "source_boundary": "derived",
        },
    }


def _write_index(repo_path: Path, *, metadata: dict[str, object] | None = None) -> None:
    output = repo_path / "graphify-out"
    output.mkdir(parents=True, exist_ok=True)
    (output / "graph.json").write_text(
        json.dumps({"nodes": [{"id": "a"}], "links": [{"source": "a", "target": "a"}]}),
        encoding="utf-8",
    )
    (output / "manifest.json").write_text("{}\n", encoding="utf-8")
    if metadata is not None:
        (output / ".softos-index.json").write_text(json.dumps(metadata), encoding="utf-8")


class CodeGraphOpsTests(unittest.TestCase):
    def test_discovers_one_and_multiple_registered_repos_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "root.py").write_text("def root(): pass\n", encoding="utf-8")
            (root / "api").mkdir()
            (root / "api" / "main.go").write_text("package main\n", encoding="utf-8")
            (root / "unmanaged").mkdir()
            (root / "unmanaged" / "secret.py").write_text("x = 1\n", encoding="utf-8")
            config = _config(
                {
                    "root": {"path": ".", "kind": "root"},
                    "api": {"path": "api", "kind": "implementation"},
                }
            )

            items = inspect_repos(root=root, workspace_config=config)

        self.assertEqual(["api", "root"], [item["repo"] for item in items])
        self.assertEqual(["api"], next(item for item in items if item["repo"] == "root")["exclusions"])
        self.assertEqual(2, next(item for item in items if item["repo"] == "root")["source_file_count"])

    def test_reports_unsupported_and_missing_project_without_aborting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs" / "README.md").write_text("# docs\n", encoding="utf-8")
            config = _config(
                {
                    "docs": {"path": "docs", "kind": "implementation"},
                    "missing": {"path": "missing", "kind": "implementation"},
                }
            )

            items = inspect_repos(root=root, workspace_config=config)

        self.assertEqual("unsupported", next(item for item in items if item["repo"] == "docs")["status"])
        self.assertEqual("error", next(item for item in items if item["repo"] == "missing")["status"])

    def test_status_transitions_from_missing_to_current_then_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "main.py"
            source.write_text("def one(): pass\n", encoding="utf-8")
            config = _config({"root": {"path": ".", "kind": "root"}})
            missing = inspect_repo("root", root=root, workspace_config=config)
            self.assertEqual("missing", missing["status"])

            metadata = {
                "repo": "root",
                "repo_path": ".",
                "exclusions": [],
                "provider": "graphify",
                "indexer_version": "0.9.56",
                "mode": "code-only",
                "source_file_count": missing["source_file_count"],
                "source_fingerprint": missing["source_fingerprint"],
                "indexed_at": "2026-09-08T00:00:00+00:00",
            }
            _write_index(root, metadata=metadata)
            self.assertEqual("current", inspect_repo("root", root=root, workspace_config=config)["status"])

            graph = root / "graphify-out" / "graph.json"
            newer = graph.stat().st_mtime_ns + 1_000_000
            source.touch()
            source_stat = source.stat()
            source.touch()
            if source.stat().st_mtime_ns <= graph.stat().st_mtime_ns:
                import os
                os.utime(source, ns=(source_stat.st_atime_ns, newer))
            self.assertEqual("stale", inspect_repo("root", root=root, workspace_config=config)["status"])

    def test_refresh_initializes_with_code_only_and_root_exclusions(self) -> None:
        commands: list[list[str]] = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "main.py").write_text("def one(): pass\n", encoding="utf-8")
            (root / "api").mkdir()
            (root / "api" / "main.py").write_text("def api(): pass\n", encoding="utf-8")
            config = _config(
                {
                    "root": {"path": ".", "kind": "root"},
                    "api": {"path": "api", "kind": "implementation"},
                }
            )

            def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                commands.append(command)
                if command[0] == "/usr/local/bin/graphify":
                    _write_index(Path(command[command.index("--out") + 1]))
                    return subprocess.CompletedProcess(command, 0, stdout="indexed\n", stderr="")
                return subprocess.CompletedProcess(command, 1, stdout="", stderr="not git")

            item = refresh_repo(
                "root",
                root=root,
                workspace_config=config,
                which=lambda name: "/usr/local/bin/graphify" if name == "graphify" else None,
                run_command=fake_run,
            )

        self.assertEqual("current", item["status"])
        self.assertEqual("init", item["operation"])
        self.assertIn("--code-only", commands[0])
        self.assertIn("--exclude", commands[0])
        self.assertIn("api", commands[0])

    def test_refresh_all_isolates_project_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("good", "bad"):
                (root / name).mkdir()
                (root / name / "main.py").write_text("x = 1\n", encoding="utf-8")
            config = _config(
                {
                    "good": {"path": "good", "kind": "implementation"},
                    "bad": {"path": "bad", "kind": "implementation"},
                }
            )

            def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                if command[0] == "/usr/local/bin/graphify":
                    repo_path = Path(command[2])
                    if repo_path.name == "bad":
                        return subprocess.CompletedProcess(command, 2, stdout="", stderr="broken parser")
                    _write_index(Path(command[command.index("--out") + 1]))
                    return subprocess.CompletedProcess(command, 0, stdout="indexed\n", stderr="")
                return subprocess.CompletedProcess(command, 1, stdout="", stderr="not git")

            rc = command_code_graph_refresh(
                Namespace(repo=None, all=True, json=True),
                root=root,
                workspace_config=config,
                json_dumps=_json_dumps,
                which=lambda name: "/usr/local/bin/graphify" if name == "graphify" else None,
                run_command=fake_run,
            )

        self.assertEqual(1, rc)

    def test_failed_refresh_preserves_previous_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "main.py").write_text("x = 1\n", encoding="utf-8")
            _write_index(root)
            graph_path = root / "graphify-out" / "graph.json"
            previous = graph_path.read_bytes()

            def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                if command[0] == "/usr/local/bin/graphify":
                    generated = Path(command[command.index("--out") + 1]) / "graphify-out"
                    generated.mkdir(parents=True)
                    (generated / "graph.json").write_text('{"nodes": []}\n', encoding="utf-8")
                    return subprocess.CompletedProcess(command, 0, stdout="partial\n", stderr="")
                return subprocess.CompletedProcess(command, 1, stdout="", stderr="not git")

            item = refresh_repo(
                "root",
                root=root,
                workspace_config=_config({"root": {"path": ".", "kind": "root"}}),
                which=lambda name: "/usr/local/bin/graphify" if name == "graphify" else None,
                run_command=fake_run,
            )

            self.assertEqual("error", item["status"])
            self.assertEqual("graphify_output_incomplete", item["error"]["code"])
            self.assertEqual(previous, graph_path.read_bytes())

    def test_doctor_is_non_blocking_when_graphify_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "main.py").write_text("x = 1\n", encoding="utf-8")
            rc = command_code_graph_doctor(
                Namespace(json=True),
                root=root,
                workspace_config=_config({"root": {"path": ".", "kind": "root"}}),
                json_dumps=_json_dumps,
                which=lambda _name: None,
            )
        self.assertEqual(0, rc)

    def test_doctor_reads_package_version_when_cli_has_no_version_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "main.py").write_text("x = 1\n", encoding="utf-8")

            def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                if command[0] == "/usr/local/bin/graphify":
                    return subprocess.CompletedProcess(command, 2, stdout="", stderr="unknown option")
                return subprocess.CompletedProcess(command, 0, stdout="0.9.56\n", stderr="")

            output = io.StringIO()
            with redirect_stdout(output):
                rc = command_code_graph_doctor(
                    Namespace(json=True),
                    root=root,
                    workspace_config=_config({"root": {"path": ".", "kind": "root"}}),
                    json_dumps=_json_dumps,
                    which=lambda name: f"/usr/local/bin/{name}",
                    run_command=fake_run,
                )

        payload = json.loads(output.getvalue())
        self.assertEqual(0, rc)
        self.assertTrue(payload["available"])
        self.assertEqual("0.9.56", payload["version"])
        self.assertTrue(payload["version_matches_config"])

    def test_workspace_mcp_configs_expose_graphify(self) -> None:
        root = Path(__file__).resolve().parents[1]
        cursor = json.loads((root / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
        opencode = json.loads((root / "opencode.json").read_text(encoding="utf-8"))
        generic = json.loads((root / ".mcp.example.json").read_text(encoding="utf-8"))

        self.assertEqual("graphify-mcp", cursor["mcpServers"]["graphify"]["command"])
        self.assertEqual("graphify-mcp", opencode["mcp"]["graphify"]["command"][0])
        self.assertEqual("graphify-mcp", generic["mcpServers"]["graphify"]["command"])


if __name__ == "__main__":
    unittest.main()
