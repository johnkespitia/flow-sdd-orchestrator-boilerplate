from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
