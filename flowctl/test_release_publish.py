from __future__ import annotations

import argparse
import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from flowctl import release


class ReleasePublishTests(unittest.TestCase):
    def test_infer_semver_bump_from_conventional_commits(self) -> None:
        commits = [
            {
                "type": "docs",
                "description": "refresh handbook",
                "breaking": False,
            },
            {
                "type": "feat",
                "description": "add release publish command",
                "breaking": False,
            },
        ]
        self.assertEqual(release._infer_semver_bump(commits), "minor")

        commits.append(
            {
                "type": "fix",
                "description": "align release state",
                "breaking": True,
            }
        )
        self.assertEqual(release._infer_semver_bump(commits), "major")

    def test_publish_updates_changelog_creates_tag_and_pushes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            remote = root / "origin.git"
            workspace = root / "workspace"

            subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True, text=True)
            subprocess.run(["git", "clone", str(remote), str(workspace)], check=True, capture_output=True, text=True)
            subprocess.run(["git", "-C", str(workspace), "config", "user.name", "Codex"], check=True)
            subprocess.run(["git", "-C", str(workspace), "config", "user.email", "codex@example.com"], check=True)
            subprocess.run(["git", "-C", str(workspace), "branch", "-M", "main"], check=True)

            changelog = workspace / "CHANGELOG.md"
            changelog.write_text(
                "# Changelog\n\n"
                "All notable changes to this project will be documented in this file.\n\n"
                "## v0.1.1 - 2026-03-28\n\n"
                "Previous release.\n",
                encoding="utf-8",
            )
            (workspace / "README.md").write_text("hello\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(workspace), "add", "CHANGELOG.md", "README.md"], check=True)
            subprocess.run(["git", "-C", str(workspace), "commit", "-m", "chore: bootstrap repo"], check=True)
            subprocess.run(["git", "-C", str(workspace), "tag", "-a", "v0.1.1", "-m", "v0.1.1"], check=True)
            subprocess.run(["git", "-C", str(workspace), "push", "origin", "main"], check=True)
            subprocess.run(["git", "-C", str(workspace), "push", "origin", "v0.1.1"], check=True)

            (workspace / "feature.txt").write_text("new feature\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(workspace), "add", "feature.txt"], check=True)
            subprocess.run(
                ["git", "-C", str(workspace), "commit", "-m", "feat(release): automate changelog publishing"],
                check=True,
            )

            args = argparse.Namespace(
                bump="auto",
                version=None,
                since_tag=None,
                skip_github=True,
                dry_run=False,
                json=True,
            )
            output = io.StringIO()
            with redirect_stdout(output):
                result = release.command_release_publish(
                    args,
                    root=workspace,
                    changelog_path=changelog,
                    utc_now=lambda: "2026-03-29T05:00:00+00:00",
                    json_dumps=lambda payload: json.dumps(payload, indent=2, ensure_ascii=True),
                )
            self.assertEqual(result, 0)
            self.assertIn('"version": "v0.2.0"', output.getvalue())

            changelog_text = changelog.read_text(encoding="utf-8")
            self.assertIn("## v0.2.0 - 2026-03-29", changelog_text)
            self.assertIn("- automate changelog publishing", changelog_text)

            local_tag = subprocess.run(
                ["git", "-C", str(workspace), "tag", "--list", "v0.2.0"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertEqual(local_tag, "v0.2.0")

            remote_tag = subprocess.run(
                ["git", "-C", str(workspace), "ls-remote", "--tags", "origin", "refs/tags/v0.2.0"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertTrue(remote_tag)


if __name__ == "__main__":
    unittest.main()
