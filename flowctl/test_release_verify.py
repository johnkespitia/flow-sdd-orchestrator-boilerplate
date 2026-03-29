from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

from flowctl import release


class ReleaseVerifyTests(unittest.TestCase):
    def test_remote_tracking_refs_containing_sha_matches_origin_main(self) -> None:
        root = Path(__file__).resolve().parents[1]
        repo_sha = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "origin/main"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        present, details = release._remote_tracking_refs_containing_sha(
            repo_path=root,
            repo_sha=repo_sha,
            remote_name="origin",
            root=root,
        )
        self.assertTrue(present)
        self.assertIn("origin/main", details)


if __name__ == "__main__":
    unittest.main()
