from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from flowctl import stack


class StackComposeFilesTests(unittest.TestCase):
    def test_find_repo_compose_file_prefers_repo_compose(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            compose_path = repo_root / "docker-compose.yml"
            compose_path.write_text("services: {}\n", encoding="utf-8")
            found = stack.find_repo_compose_file(repo_root)
            self.assertEqual(found, compose_path.resolve())

    def test_workspace_compose_files_includes_external_repo_compose(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            root_compose = root / ".devcontainer" / "docker-compose.yml"
            root_compose.parent.mkdir(parents=True, exist_ok=True)
            root_compose.write_text("services: {}\n", encoding="utf-8")

            repo_root = root / "projects" / "api"
            repo_root.mkdir(parents=True, exist_ok=True)
            external_compose = repo_root / "docker-compose.yml"
            external_compose.write_text("services: {}\n", encoding="utf-8")

            workspace_config = {
                "repos": {
                    "root": {"path": ".", "kind": "root"},
                    "api": {"path": "projects/api", "kind": "implementation", "compose_service": "api"},
                }
            }
            files = stack.workspace_compose_files(root_compose, workspace_config)
            self.assertEqual(files, [root_compose.resolve(), external_compose.resolve()])

    def test_compose_base_command_renders_all_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            primary = root / ".devcontainer" / "docker-compose.yml"
            secondary = root / "projects" / "api" / "docker-compose.yml"
            primary.parent.mkdir(parents=True, exist_ok=True)
            secondary.parent.mkdir(parents=True, exist_ok=True)
            primary.write_text("services: {}\n", encoding="utf-8")
            secondary.write_text("services: {}\n", encoding="utf-8")

            command = stack.compose_base_command("softos", [primary, secondary], compose_command=["docker", "compose"])
            self.assertEqual(
                command,
                [
                    "docker",
                    "compose",
                    "-p",
                    "softos",
                    "--project-directory",
                    str(primary.resolve().parent),
                    "-f",
                    str(primary.resolve()),
                    "-f",
                    str(secondary.resolve()),
                ],
            )

    def test_compose_base_command_can_render_standalone_docker_compose(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            primary = root / ".devcontainer" / "docker-compose.yml"
            primary.parent.mkdir(parents=True, exist_ok=True)
            primary.write_text("services: {}\n", encoding="utf-8")

            command = stack.compose_base_command("softos", [primary], compose_command=["docker-compose"])

            self.assertEqual(
                command,
                [
                    "docker-compose",
                    "-p",
                    "softos",
                    "--project-directory",
                    str(primary.resolve().parent),
                    "-f",
                    str(primary.resolve()),
                ],
            )

    def test_compose_command_prefix_prefers_plugin_when_available(self) -> None:
        completed = Mock(returncode=0)
        with patch("flowctl.stack.shutil.which", side_effect=lambda name: "/bin/docker" if name == "docker" else None):
            with patch("flowctl.stack.subprocess.run", return_value=completed) as run:
                self.assertEqual(["docker", "compose"], stack.compose_command_prefix())
                run.assert_called_once_with(
                    ["docker", "compose", "version"],
                    capture_output=True,
                    text=True,
                    check=False,
                )

    def test_compose_command_prefix_falls_back_to_standalone(self) -> None:
        completed = Mock(returncode=1)

        def _which(name: str) -> str | None:
            if name == "docker":
                return "/bin/docker"
            if name == "docker-compose":
                return "/usr/local/bin/docker-compose"
            return None

        with patch("flowctl.stack.shutil.which", side_effect=_which):
            with patch("flowctl.stack.subprocess.run", return_value=completed):
                self.assertEqual(["docker-compose"], stack.compose_command_prefix())


if __name__ == "__main__":
    unittest.main()
