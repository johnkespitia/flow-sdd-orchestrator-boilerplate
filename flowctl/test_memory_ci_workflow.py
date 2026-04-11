from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "memory-smoke.yml"


class MemoryCiWorkflowTests(unittest.TestCase):
    def test_memory_smoke_workflow_is_manual_only(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("pull_request:", text)
        self.assertNotIn("push:", text)

    def test_memory_smoke_workflow_runs_inside_workspace_devcontainer(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("docker compose -f .devcontainer/docker-compose.yml build workspace", text)
        self.assertIn("docker compose -f .devcontainer/docker-compose.yml up -d workspace", text)
        self.assertIn("scripts/workspace_exec.sh python3 ./flow memory doctor --json", text)
        self.assertIn("scripts/workspace_exec.sh python3 ./flow memory smoke --json", text)


if __name__ == "__main__":
    unittest.main()
