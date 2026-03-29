from __future__ import annotations

import unittest

from flowctl.repo_ci_matrix import build_repo_ci_matrices


class RepoCiMatrixTests(unittest.TestCase):
    def test_build_repo_ci_matrices_splits_generic_and_delegated(self) -> None:
        workspace_config = {
            "repos": {
                "root": {"path": ".", "kind": "root"},
                "api": {
                    "path": "projects/api",
                    "kind": "implementation",
                    "runtime": "python",
                    "ci": {
                        "mode": "workflow-dispatch",
                        "workflow": "repo-ci.yml",
                        "trigger_mode": "workflow_dispatch_only",
                        "inputs": {"repo": "api"},
                    },
                },
                "web": {
                    "path": "projects/web",
                    "kind": "implementation",
                    "runtime": "pnpm",
                },
            }
        }
        runtime_packs = {
            "python": {"test_runner": "pytest"},
            "pnpm": {"test_runner": "pnpm"},
        }

        payload = build_repo_ci_matrices(workspace_config, runtime_packs)
        self.assertTrue(payload["has_generic"])
        self.assertTrue(payload["has_delegated"])
        self.assertEqual(payload["generic"]["include"][0]["repo"], "web")
        self.assertEqual(payload["delegated"]["include"][0]["repo"], "api")
        self.assertEqual(payload["delegated"]["include"][0]["workflow"], "repo-ci.yml")
        self.assertEqual(payload["delegated"]["include"][0]["trigger_mode"], "workflow_dispatch_only")


if __name__ == "__main__":
    unittest.main()
