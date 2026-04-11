from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
import json


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "bootstrap_workspace.py"
SPEC = importlib.util.spec_from_file_location("bootstrap_workspace", SCRIPT_PATH)
BOOTSTRAP = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(BOOTSTRAP)


class BootstrapWorkspaceTests(unittest.TestCase):
    def test_rewrite_project_texts_updates_agent_context_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            destination = Path(tmp_dir)
            source_config = {
                "project": {
                    "display_name": "Flow SDD Orchestrator Boilerplate",
                    "root_repo": "sdd-workspace-boilerplate",
                }
            }

            files = {
                destination / "AGENTS.md": "Flow SDD Orchestrator Boilerplate :: sdd-workspace-boilerplate\n",
                destination / "OPENCODE.md": "Flow SDD Orchestrator Boilerplate :: sdd-workspace-boilerplate\n",
                destination / ".cursor" / "rules" / "softos.mdc": "Flow SDD Orchestrator Boilerplate :: sdd-workspace-boilerplate\n",
                destination / ".agents" / "skills" / "softos-agent-playbook" / "SKILL.md": "Flow SDD Orchestrator Boilerplate :: sdd-workspace-boilerplate\n",
            }
            for path, content in files.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

            BOOTSTRAP.rewrite_project_texts(
                destination,
                source_config,
                project_name="Nuevo Workspace",
                root_repo="nuevo-root-repo",
            )

            for path in files:
                text = path.read_text(encoding="utf-8")
                self.assertIn("Nuevo Workspace", text)
                self.assertIn("nuevo-root-repo", text)
                self.assertNotIn("Flow SDD Orchestrator Boilerplate", text)
                self.assertNotIn("sdd-workspace-boilerplate", text)

    def test_rewrite_workspace_config_sets_project_scoped_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            destination = Path(tmp_dir)
            source_config = {
                "project": {
                    "display_name": "Flow SDD Orchestrator Boilerplate",
                    "root_repo": "sdd-workspace-boilerplate",
                },
                "repos": {
                    "sdd-workspace-boilerplate": {
                        "path": ".",
                        "kind": "root",
                        "target_roots": [],
                        "default_targets": [],
                    }
                },
            }

            BOOTSTRAP.rewrite_workspace_config(
                destination,
                source_config,
                project_name="Nuevo Workspace",
                root_repo="nuevo-root-repo",
            )

            payload = json.loads((destination / "workspace.config.json").read_text(encoding="utf-8"))
            self.assertEqual("nuevo-root-repo", payload["memory"]["agent"]["project"])
            self.assertEqual(".flow/memory/engram", payload["memory"]["agent"]["data_dir"])
            target_roots = payload["repos"]["nuevo-root-repo"]["target_roots"]
            self.assertIn(".devcontainer", target_roots)
            self.assertIn(".flow/memory", target_roots)
            self.assertIn(".mcp.example.json", target_roots)

    def test_patch_engram_project_updates_compose_and_mcp_example(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            destination = Path(tmp_dir)
            compose = destination / ".devcontainer" / "docker-compose.yml"
            mcp = destination / ".mcp.example.json"
            compose.parent.mkdir(parents=True, exist_ok=True)
            compose.write_text(
                "ENGRAM_PROJECT: ${ENGRAM_PROJECT:-softos-sdd-orchestrator}\n",
                encoding="utf-8",
            )
            mcp.write_text('{"project":"softos-sdd-orchestrator"}\n', encoding="utf-8")

            BOOTSTRAP.patch_engram_project(destination, "nuevo-root-repo")

            self.assertIn("ENGRAM_PROJECT: ${ENGRAM_PROJECT:-nuevo-root-repo}", compose.read_text(encoding="utf-8"))
            self.assertIn("nuevo-root-repo", mcp.read_text(encoding="utf-8"))
            self.assertNotIn("softos-sdd-orchestrator", mcp.read_text(encoding="utf-8"))

    def test_reset_flow_state_creates_memory_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            destination = Path(tmp_dir)

            BOOTSTRAP.reset_flow_state(destination)

            self.assertTrue((destination / ".flow" / "memory" / ".gitkeep").is_file())


if __name__ == "__main__":
    unittest.main()
