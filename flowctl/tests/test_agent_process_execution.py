from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from flowctl.agent_executors import AgentRegistryError, command_agent_run, load_agent_registry
from flowctl.agent_process_execution import (
    AgentRunError,
    AgentRunMetadata,
    OPENCODE_CONFIG_CONTENT_ENV,
    execute_subprocess,
    merge_process_environment,
    prepare_agent_run,
    probe_opencode_models,
    resolve_resource_model,
    resolve_target_within_workdir,
    run_agent_process,
    validate_process_env_overlay,
    validate_workdir,
)
from flowctl.agent_executor_adapters import (
    EXECUTION_CONTRACT_BEGIN,
    AgentAdapterInvocation,
    AgentRunRequest,
    GenericStdinAdapter,
    build_execution_contract,
)
from flowctl.agent_executors import AgentExecutor
from flowctl.tooling import HOST_EXECUTION_BLOCK_MESSAGE


def _write_config(root: Path, *, agents: object | None = None, repos: object | None = None) -> Path:
    payload: dict[str, object] = {
        "project": {"display_name": "Test", "root_repo": "softos-agentic"},
        "repos": repos
        or {
            "softos-agentic": {"path": ".", "kind": "root"},
        },
    }
    if agents is not None:
        payload["agents"] = agents
    path = root / "workspace.config.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_fake_executor(path: Path) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "if len(sys.argv) > 1 and sys.argv[1].isdigit():\n"
        "    code = int(sys.argv[1])\n"
        "else:\n"
        "    code = 0\n"
        "sys.stdout.write('FAKE_STDOUT')\n"
        "sys.stderr.write('FAKE_STDERR')\n"
        "if not sys.stdin.isatty():\n"
        "    sys.stdin.read()\n"
        "raise SystemExit(code)\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=path, capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "agent-test@softos.test"],
        check=True,
    )
    subprocess.run(["git", "-C", str(path), "config", "user.name", "agent-test"], check=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "--allow-empty", "-m", "init"],
        capture_output=True,
        check=True,
    )


def _add_git_worktree(repo_root: Path, worktree_path: Path, branch: str = "demo/test") -> None:
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "worktree",
            "add",
            "-b",
            branch,
            str(worktree_path),
        ],
        capture_output=True,
        check=True,
    )


class PathContainmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _init_git_repo(self.root)
        self.worktree_root = self.root / ".worktrees"
        self.worktree = self.worktree_root / "softos-agentic-demo-slice"
        _add_git_worktree(self.root, self.worktree)
        (self.worktree / "allowed.txt").write_text("ok", encoding="utf-8")

    def tearDown(self) -> None:
        subprocess.run(
            ["git", "-C", str(self.root), "worktree", "remove", "--force", str(self.worktree)],
            capture_output=True,
            check=False,
        )
        self.tmp.cleanup()

    def test_valid_repo_root_and_worktree_are_accepted(self) -> None:
        validate_workdir(
            str(self.root),
            workspace_root=self.root,
            repo_root_path=self.root,
        )
        validate_workdir(
            str(self.worktree),
            workspace_root=self.root,
            repo_root_path=self.root,
        )

    def test_fake_worktree_directory_is_rejected(self) -> None:
        fake = self.worktree_root / "softos-agentic-fake-slice"
        fake.mkdir(parents=True)
        with self.assertRaisesRegex(AgentRunError, "worktree reconocido"):
            validate_workdir(
                str(fake),
                workspace_root=self.root,
                repo_root_path=self.root,
            )

    def test_nested_directory_inside_worktree_is_rejected(self) -> None:
        nested = self.worktree / "nested"
        nested.mkdir()
        with self.assertRaisesRegex(AgentRunError, "worktree reconocido"):
            validate_workdir(
                str(nested),
                workspace_root=self.root,
                repo_root_path=self.root,
            )

    def test_target_inside_worktree_is_accepted(self) -> None:
        relative = resolve_target_within_workdir(self.worktree, "allowed.txt")
        self.assertEqual("allowed.txt", relative)

    def test_prospective_target_inside_worktree_is_accepted(self) -> None:
        relative = resolve_target_within_workdir(self.worktree, "future/nested/file.py")
        self.assertEqual("future/nested/file.py", relative)

    def test_absolute_target_is_rejected_even_inside_workdir(self) -> None:
        absolute = str((self.worktree / "allowed.txt").resolve())
        with self.assertRaisesRegex(AgentRunError, "fuera de limites"):
            resolve_target_within_workdir(self.worktree, absolute)

    def test_target_outside_worktree_is_rejected(self) -> None:
        outside = self.root / "outside.txt"
        outside.write_text("nope", encoding="utf-8")
        with self.assertRaisesRegex(AgentRunError, "fuera de limites"):
            resolve_target_within_workdir(self.worktree, "../outside.txt")

    def test_parent_traversal_target_is_rejected(self) -> None:
        with self.assertRaisesRegex(AgentRunError, "fuera de limites"):
            resolve_target_within_workdir(self.worktree, "../outside.txt")

    def test_symlink_escape_is_rejected(self) -> None:
        outside = self.root / "secret.txt"
        outside.write_text("secret", encoding="utf-8")
        link = self.worktree / "escape-link"
        link.symlink_to(outside)
        with self.assertRaisesRegex(AgentRunError, "fuera de limites"):
            resolve_target_within_workdir(self.worktree, "escape-link")

    def test_prospective_path_beneath_symlink_escape_is_rejected(self) -> None:
        outside = self.root / "secret.txt"
        outside.write_text("secret", encoding="utf-8")
        link = self.worktree / "escape-link"
        link.symlink_to(outside)
        with self.assertRaisesRegex(AgentRunError, "fuera de limites"):
            resolve_target_within_workdir(self.worktree, "escape-link/nested.py")

    def test_dangling_symlink_escape_is_rejected(self) -> None:
        outside = self.root / "missing-outside.txt"
        link = self.worktree / "dangling-escape"
        link.symlink_to(outside)
        with self.assertRaisesRegex(AgentRunError, "fuera de limites"):
            resolve_target_within_workdir(self.worktree, "dangling-escape")

    def test_chained_symlink_to_external_existing_target_is_rejected(self) -> None:
        outside = self.root / "secret.txt"
        outside.write_text("secret", encoding="utf-8")
        link_b = self.worktree / "link-b"
        link_b.symlink_to(outside)
        link_a = self.worktree / "link-a"
        link_a.symlink_to("link-b")
        with self.assertRaisesRegex(AgentRunError, "fuera de limites"):
            resolve_target_within_workdir(self.worktree, "link-a")

    def test_chained_symlink_to_external_dangling_target_is_rejected(self) -> None:
        outside = self.root / "missing-outside.txt"
        link_b = self.worktree / "link-b"
        link_b.symlink_to(outside)
        link_a = self.worktree / "link-a"
        link_a.symlink_to("link-b")
        with self.assertRaisesRegex(AgentRunError, "fuera de limites"):
            resolve_target_within_workdir(self.worktree, "link-a")

    def test_prospective_path_beneath_chained_escaping_symlink_is_rejected(self) -> None:
        outside = self.root / "secret.txt"
        outside.write_text("secret", encoding="utf-8")
        link_b = self.worktree / "link-b"
        link_b.symlink_to(outside)
        link_a = self.worktree / "link-a"
        link_a.symlink_to("link-b")
        with self.assertRaisesRegex(AgentRunError, "fuera de limites"):
            resolve_target_within_workdir(self.worktree, "link-a/nested.py")

    def test_repo_worktree_mismatch_is_rejected(self) -> None:
        backend_root = self.root / "backend"
        backend_root.mkdir()
        _init_git_repo(backend_root)
        other_worktree = self.worktree_root / "backend-demo-slice"
        _add_git_worktree(backend_root, other_worktree, branch="demo/backend")
        with self.assertRaisesRegex(AgentRunError, "worktree reconocido"):
            validate_workdir(
                str(other_worktree),
                workspace_root=self.root,
                repo_root_path=self.root,
            )
        subprocess.run(
            ["git", "-C", str(backend_root), "worktree", "remove", "--force", str(other_worktree)],
            capture_output=True,
            check=False,
        )


class SubprocessExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.fake = self.root / "fake-agent"
        _write_fake_executor(self.fake)
        self.test_adapter = GenericStdinAdapter(adapter_name="test")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_argv_invocation_uses_shell_false(self) -> None:
        captured: dict[str, object] = {}

        def fake_run(**kwargs: object) -> object:
            captured.update(kwargs)
            return subprocess.CompletedProcess(args=kwargs["args"], returncode=0, stdout=b"", stderr=b"")

        execute_subprocess(
            AgentAdapterInvocation(argv=(str(self.fake), "0"), stdin="prompt"),
            cwd=self.root,
            subprocess_run=fake_run,
        )
        self.assertEqual(list(captured["args"]), [str(self.fake), "0"])
        self.assertIs(captured["shell"], False)
        self.assertEqual(b"prompt", captured["input"])

    def test_stdout_and_stderr_are_captured_without_extra_newlines(self) -> None:
        streams: dict[str, bytes] = {}

        def writer(stream: str, payload: bytes) -> None:
            streams[stream] = payload

        executor = AgentExecutor(
            executor_id="test",
            adapter="test",
            executable=str(self.fake),
            argv=("0",),
        )
        with mock.patch(
            "flowctl.agent_process_execution.resolve_adapter",
            return_value=self.test_adapter,
        ):
            exit_code, _metadata = run_agent_process(
                executor=executor,
                repo="softos-agentic",
                workspace_root=self.root,
                workdir=self.root,
                targets=("allowed.txt",),
                prompt="operator prompt",
                shutil_which=lambda _: None,
                subprocess_run=subprocess.run,
                stream_writer=writer,
            )
        self.assertEqual(0, exit_code)
        self.assertEqual(b"FAKE_STDOUT", streams["stdout"])
        self.assertEqual(b"FAKE_STDERR", streams["stderr"])

    def test_child_exit_code_is_propagated_exactly(self) -> None:
        for expected in (0, 1, 37):
            with self.subTest(expected=expected):
                with mock.patch(
                    "flowctl.agent_process_execution.resolve_adapter",
                    return_value=GenericStdinAdapter(adapter_name="test"),
                ):
                    exit_code, _metadata = run_agent_process(
                        executor=AgentExecutor(
                            executor_id="test",
                            adapter="test",
                            executable=str(self.fake),
                            argv=(str(expected),),
                        ),
                        repo="softos-agentic",
                        workspace_root=self.root,
                        workdir=self.root,
                        targets=("allowed.txt",),
                        prompt="operator prompt",
                        shutil_which=lambda _: None,
                        subprocess_run=subprocess.run,
                    )
                self.assertEqual(expected, exit_code)

    def test_invalid_utf8_child_output_preserves_exact_bytes_and_exit_code(self) -> None:
        noisy = self.root / "noisy-agent"
        noisy.write_bytes(
            b"#!/usr/bin/env python3\n"
            b"import sys\n"
            b"sys.stdout.buffer.write(b'\\xff\\xfe')\n"
            b"raise SystemExit(17)\n"
        )
        noisy.chmod(noisy.stat().st_mode | stat.S_IXUSR)
        executor = AgentExecutor(
            executor_id="test",
            adapter="test",
            executable=str(noisy),
            argv=(),
        )
        streams: dict[str, bytes] = {}

        def writer(stream: str, payload: bytes) -> None:
            streams[stream] = payload

        with mock.patch(
            "flowctl.agent_process_execution.resolve_adapter",
            return_value=self.test_adapter,
        ):
            exit_code, _metadata = run_agent_process(
                executor=executor,
                repo="softos-agentic",
                workspace_root=self.root,
                workdir=self.root,
                targets=("allowed.txt",),
                prompt="operator prompt",
                shutil_which=lambda _: None,
                subprocess_run=subprocess.run,
                stream_writer=writer,
            )
        self.assertEqual(17, exit_code)
        self.assertEqual(b"\xff\xfe", streams["stdout"])

    def test_process_creation_failure_is_deterministic(self) -> None:
        executor = AgentExecutor(
            executor_id="test",
            adapter="test",
            executable=str(self.fake),
            argv=(),
        )

        def failing_run(**kwargs: object) -> object:
            raise FileNotFoundError("vanished")

        with mock.patch(
            "flowctl.agent_process_execution.resolve_adapter",
            return_value=self.test_adapter,
        ):
            with self.assertRaisesRegex(AgentRunError, "fallo al crear el proceso hijo"):
                run_agent_process(
                    executor=executor,
                    repo="softos-agentic",
                    workspace_root=self.root,
                    workdir=self.root,
                    targets=("allowed.txt",),
                    prompt="operator prompt",
                    shutil_which=lambda _: str(self.fake),
                    subprocess_run=failing_run,
                )

    def test_missing_executable_after_readiness_check_is_deterministic(self) -> None:
        secret_prompt = "SUPER_SECRET_PROMPT_TOKEN"
        secret_env = "SUPER_SECRET_ENV_TOKEN"
        secret_argv = "SUPER_SECRET_ARGV_TOKEN"
        executor = AgentExecutor(
            executor_id="test",
            adapter="test",
            executable=str(self.fake),
            argv=(secret_argv,),
        )

        def failing_run(**kwargs: object) -> object:
            raise FileNotFoundError("vanished")

        with mock.patch(
            "flowctl.agent_process_execution.resolve_adapter",
            return_value=self.test_adapter,
        ):
            with mock.patch.dict(os.environ, {"TEST_AGENT_SECRET": secret_env}, clear=False):
                with self.assertRaises(AgentRunError) as ctx:
                    run_agent_process(
                        executor=executor,
                        repo="softos-agentic",
                        workspace_root=self.root,
                        workdir=self.root,
                        targets=("allowed.txt",),
                        prompt=secret_prompt,
                        shutil_which=lambda _: None,
                        subprocess_run=failing_run,
                    )
        diagnostic = str(ctx.exception)
        self.assertIn("fallo al crear el proceso hijo", diagnostic)
        self.assertNotIn("no esta disponible", diagnostic)
        self.assertNotIn(secret_prompt, diagnostic)
        self.assertNotIn(secret_env, diagnostic)
        self.assertNotIn(secret_argv, diagnostic)


class ExecutionContractTests(unittest.TestCase):
    def test_contract_contains_required_fields_and_sorted_targets(self) -> None:
        executor = AgentExecutor(
            executor_id="codex",
            adapter="codex",
            executable="codex",
            argv=(),
        )
        contract = build_execution_contract(
            request=AgentRunRequest(
                executor=executor,
                repo="softos-agentic",
                workspace_root="/workspace",
                workdir="/workspace/.worktrees/demo",
                targets=("b.txt", "a.txt"),
                user_prompt="do work",
                contract_body="",
            )
        )
        self.assertIn(EXECUTION_CONTRACT_BEGIN, contract)
        self.assertIn("executor: codex", contract)
        self.assertIn("repository: softos-agentic", contract)
        self.assertIn("workspace_root: /workspace", contract)
        self.assertIn("workdir: /workspace/.worktrees/demo", contract)
        self.assertIn("  - a.txt", contract)
        self.assertIn("  - b.txt", contract)
        self.assertIn(
            "python3 ./flow repo exec --workdir /workspace/.worktrees/demo softos-agentic -- <command>",
            contract,
        )
        self.assertIn("scripts/workspace_exec.sh python3 ./flow <command>", contract)
        self.assertIn("python3 ./flow stack <command>", contract)


class SensitiveMaterialTests(unittest.TestCase):
    def test_metadata_excludes_prompt_streams_and_argv(self) -> None:
        metadata = AgentRunMetadata(
            executor_id="codex",
            repo="softos-agentic",
            workdir="/workspace/.worktrees/demo",
            targets=("flowctl/agent_executors.py",),
            started_at="2026-01-01T00:00:00+00:00",
            finished_at="2026-01-01T00:00:01+00:00",
            exit_code=0,
            resource_id="opencode-free",
        )
        payload = metadata.__dict__
        forbidden_keys = {"prompt", "stdout", "stderr", "argv", "environment", "env"}
        self.assertTrue(forbidden_keys.isdisjoint(payload.keys()))
        self.assertEqual("opencode-free", metadata.resource_id)

    def test_command_run_does_not_persist_sensitive_material_on_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reports = root / ".flow" / "reports"
            reports.mkdir(parents=True)
            fake = root / "fake-agent"
            _write_fake_executor(fake)
            secret_prompt = "SUPER_SECRET_PROMPT_TOKEN"
            secret_env = "SUPER_SECRET_ENV_TOKEN"
            secret_argv = "SUPER_SECRET_ARGV_TOKEN"
            config = _write_config(
                root,
                agents={
                    "schema_version": 1,
                    "executors": {
                        "codex": {
                            "adapter": "codex",
                            "executable": str(fake),
                            "argv": [secret_argv],
                        },
                    },
                },
            )
            (root / "target.txt").write_text("x", encoding="utf-8")

            with mock.patch.dict(os.environ, {"TEST_AGENT_SECRET": secret_env}, clear=False):
                with mock.patch(
                    "flowctl.agent_process_execution.resolve_adapter",
                    return_value=GenericStdinAdapter(adapter_name="test"),
                ):
                    rc = command_agent_run(
                        argparse_namespace(
                            executor="codex",
                            repo="workspace-root",
                            workdir=str(root),
                            prompt=secret_prompt,
                            target=["target.txt"],
                        ),
                        workspace_root=root,
                        workspace_config_file=config,
                        workspace_config=json.loads(config.read_text(encoding="utf-8")),
                        worktree_root=root / ".worktrees",
                        root_repo="softos-agentic",
                        repo_names=["softos-agentic"],
                        shutil_which=lambda _: None,
                        subprocess_run=subprocess.run,
                    )

            self.assertEqual(0, rc)
            persisted = "".join(path.read_text(encoding="utf-8") for path in reports.rglob("*") if path.is_file())
            self.assertNotIn(secret_prompt, persisted)
            self.assertNotIn(secret_env, persisted)
            self.assertNotIn(secret_argv, persisted)

    def test_validation_failure_does_not_echo_sensitive_material(self) -> None:
        secret_prompt = "SUPER_SECRET_PROMPT_TOKEN"
        secret_env = "SUPER_SECRET_ENV_TOKEN"
        secret_argv = "SUPER_SECRET_ARGV_TOKEN"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = _write_config(
                root,
                agents={
                    "schema_version": 1,
                    "executors": {
                        "codex": {
                            "adapter": "codex",
                            "executable": "codex",
                            "argv": [secret_argv],
                        },
                    },
                },
            )
            with mock.patch.dict(os.environ, {"TEST_AGENT_SECRET": secret_env}, clear=False):
                with self.assertRaises(SystemExit) as ctx:
                    command_agent_run(
                        argparse_namespace(
                            executor="codex",
                            repo="workspace-root",
                            workdir=str(root),
                            prompt=secret_prompt,
                            target=["../outside.txt"],
                        ),
                        workspace_root=root,
                        workspace_config_file=config,
                        workspace_config=json.loads(config.read_text(encoding="utf-8")),
                        worktree_root=root / ".worktrees",
                        root_repo="softos-agentic",
                        repo_names=["softos-agentic"],
                        shutil_which=lambda _: None,
                        subprocess_run=subprocess.run,
                    )
            diagnostic = str(ctx.exception)
            self.assertNotIn(secret_prompt, diagnostic)
            self.assertNotIn(secret_env, diagnostic)
            self.assertNotIn(secret_argv, diagnostic)

    def test_missing_executable_does_not_echo_sensitive_material(self) -> None:
        secret_prompt = "SUPER_SECRET_PROMPT_TOKEN"
        secret_env = "SUPER_SECRET_ENV_TOKEN"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing_executable = str((root / "missing-executor").resolve())
            config = _write_config(
                root,
                agents={
                    "schema_version": 1,
                    "executors": {
                        "codex": {
                            "adapter": "codex",
                            "executable": missing_executable,
                            "argv": [],
                        },
                    },
                },
            )
            (root / "target.txt").write_text("x", encoding="utf-8")
            with mock.patch.dict(os.environ, {"TEST_AGENT_SECRET": secret_env}, clear=False):
                with self.assertRaises(SystemExit) as ctx:
                    command_agent_run(
                        argparse_namespace(
                            executor="codex",
                            repo="workspace-root",
                            workdir=str(root),
                            prompt=secret_prompt,
                            target=["target.txt"],
                        ),
                        workspace_root=root,
                        workspace_config_file=config,
                        workspace_config=json.loads(config.read_text(encoding="utf-8")),
                        worktree_root=root / ".worktrees",
                        root_repo="softos-agentic",
                        repo_names=["softos-agentic"],
                        shutil_which=lambda _: None,
                        subprocess_run=subprocess.run,
                    )
            diagnostic = str(ctx.exception)
            self.assertNotIn(secret_prompt, diagnostic)
            self.assertNotIn(secret_env, diagnostic)
            self.assertIn("no esta disponible", diagnostic)


class ExecutorResolutionTests(unittest.TestCase):
    def test_unknown_executor_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = _write_config(
                root,
                agents={
                    "schema_version": 1,
                    "executors": {
                        "codex": {"adapter": "codex", "executable": "codex", "argv": []},
                    },
                },
            )
            workspace_config = json.loads(config.read_text(encoding="utf-8"))
            with self.assertRaisesRegex(AgentRunError, "Executor desconocido: `missing`"):
                prepare_agent_run(
                    executor_id="missing",
                    repo_raw="softos-agentic",
                    workdir_raw=str(root),
                    prompt_raw="prompt",
                    target_raws=["."],
                    workspace_root=root,
                    workspace_config_file=config,
                    workspace_config=workspace_config,
                    root_repo="softos-agentic",
                )

    def test_missing_registry_section_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "workspace.config.json"
            config.write_text(
                json.dumps(
                    {
                        "project": {"display_name": "Test", "root_repo": "softos-agentic"},
                        "repos": {"softos-agentic": {"path": ".", "kind": "root"}},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(AgentRegistryError):
                load_agent_registry(config)

    def test_v1_adapter_reports_missing_executable_when_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = _write_config(
                root,
                agents={
                    "schema_version": 1,
                    "executors": {
                        "codex": {"adapter": "codex", "executable": "codex", "argv": []},
                    },
                },
            )
            workspace_config = json.loads(config.read_text(encoding="utf-8"))
            (root / "target.txt").write_text("x", encoding="utf-8")
            executor, repo, workdir, targets, prompt = prepare_agent_run(
                executor_id="codex",
                repo_raw="workspace-root",
                workdir_raw=str(root),
                prompt_raw="prompt",
                target_raws=["target.txt"],
                workspace_root=root,
                workspace_config_file=config,
                workspace_config=workspace_config,
                root_repo="softos-agentic",
            )
            with self.assertRaises(AgentRunError) as ctx:
                run_agent_process(
                    executor=executor,
                    repo=repo,
                    workspace_root=root,
                    workdir=workdir,
                    targets=targets,
                    prompt=prompt,
                    shutil_which=lambda _: None,
                    subprocess_run=subprocess.run,
                )
            diagnostic = str(ctx.exception)
            self.assertIn("no esta disponible", diagnostic)

    def test_v1_adapter_run_launches_with_fake_executable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = root / "fake-codex"
            _write_fake_executor(fake)
            config = _write_config(
                root,
                agents={
                    "schema_version": 1,
                    "executors": {
                        "codex": {"adapter": "codex", "executable": str(fake), "argv": []},
                    },
                },
            )
            workspace_config = json.loads(config.read_text(encoding="utf-8"))
            (root / "target.txt").write_text("x", encoding="utf-8")
            executor, repo, workdir, targets, prompt = prepare_agent_run(
                executor_id="codex",
                repo_raw="workspace-root",
                workdir_raw=str(root),
                prompt_raw="prompt",
                target_raws=["target.txt"],
                workspace_root=root,
                workspace_config_file=config,
                workspace_config=workspace_config,
                root_repo="softos-agentic",
            )
            exit_code, _metadata = run_agent_process(
                executor=executor,
                repo=repo,
                workspace_root=root,
                workdir=workdir,
                targets=targets,
                prompt=prompt,
                shutil_which=lambda _: str(fake),
                subprocess_run=subprocess.run,
            )
            self.assertEqual(0, exit_code)

class CommandAgentRunIntegrationTests(unittest.TestCase):
    def test_prepare_agent_run_normalizes_targets_in_lexical_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "b.txt").write_text("b", encoding="utf-8")
            (root / "a.txt").write_text("a", encoding="utf-8")
            config = _write_config(
                root,
                agents={
                    "schema_version": 1,
                    "executors": {
                        "codex": {"adapter": "codex", "executable": "codex", "argv": []},
                    },
                },
            )
            workspace_config = json.loads(config.read_text(encoding="utf-8"))
            _executor, _repo, workdir, targets, prompt = prepare_agent_run(
                executor_id="codex",
                repo_raw="workspace-root",
                workdir_raw=str(root),
                prompt_raw="  do it  ",
                target_raws=["b.txt", "a.txt"],
                workspace_root=root,
                workspace_config_file=config,
                workspace_config=workspace_config,
                root_repo="softos-agentic",
            )
            self.assertEqual(("a.txt", "b.txt"), targets)
            self.assertEqual("  do it  ", prompt)
            self.assertEqual(root.resolve(), workdir.resolve())


class HostNativeRoutingTests(unittest.TestCase):
    def test_flow_agent_run_stays_host_native_without_container(self) -> None:
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            codex = bin_dir / "codex"
            _write_fake_executor(codex)
            env = {
                **dict(os.environ),
                "FLOW_FORCE_WORKSPACE_EXEC": "1",
                "FLOW_WORKSPACE_PATH": "/definitely-not-this-worktree",
                "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            }
            env.pop("GITHUB_ACTIONS", None)
            completed = subprocess.run(
                [
                    "python3",
                    str(root / "flow"),
                    "agent",
                    "run",
                    "codex",
                    "--repo",
                    "workspace-root",
                    "--workdir",
                    str(root),
                    "--prompt",
                    "host-native probe",
                    "--target",
                    "flowctl/agent_process_execution.py",
                ],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertNotIn(HOST_EXECUTION_BLOCK_MESSAGE, completed.stderr)
        self.assertEqual(0, completed.returncode, completed.stderr + completed.stdout)
        self.assertIn("FAKE_STDOUT", completed.stdout)


def argparse_namespace(**kwargs: object) -> object:
    class Namespace:
        pass

    ns = Namespace()
    for key, value in kwargs.items():
        setattr(ns, key, value)
    return ns


def _default_agent_resources() -> dict[str, object]:
    return {
        "schema_version": 1,
        "resources": {
            "opencode-local": {
                "executor": "opencode-local",
                "capabilities": ["tool_calling", "write", "local_execution"],
                "capacity": 1,
                "cost_tier": "local",
                "selection_priority": 10,
                "model_resolution": "worker_profile",
                "data_sensitivity": "local-only",
            },
            "opencode-free": {
                "executor": "opencode",
                "capabilities": ["tool_calling", "write", "cloud_execution"],
                "capacity": 1,
                "cost_tier": "cloud/free",
                "selection_priority": 20,
                "model_resolution": "dynamic_free",
                "data_sensitivity": "cloud-eligible",
                "candidate_tie_break": "lexical",
            },
            "opencode-go": {
                "executor": "opencode",
                "capabilities": ["tool_calling", "write", "cloud_execution", "architecture"],
                "capacity": 1,
                "cost_tier": "cloud/paid-low",
                "selection_priority": 30,
                "model_resolution": "dynamic_go",
                "data_sensitivity": "cloud-eligible",
                "candidate_tie_break": "lexical",
            },
        },
    }


def _write_resource_config(root: Path, *, fake_executable: Path) -> Path:
    payload: dict[str, object] = {
        "project": {"display_name": "Test", "root_repo": "softos-agentic"},
        "repos": {"softos-agentic": {"path": ".", "kind": "root"}},
        "agents": {
            "schema_version": 1,
            "executors": {
                "codex": {"adapter": "codex", "executable": "codex", "argv": []},
                "opencode": {
                    "adapter": "opencode",
                    "executable": str(fake_executable),
                    "argv": [],
                },
                "opencode-local": {
                    "adapter": "opencode",
                    "executable": str(fake_executable),
                    "argv": [],
                },
            },
        },
        "agent_resources": _default_agent_resources(),
    }
    path = root / "workspace.config.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class ResourceProcessOverlayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.fake = self.root / "fake-opencode"
        _write_fake_executor(self.fake)
        self.config = _write_resource_config(self.root, fake_executable=self.fake)
        self.workspace_config = json.loads(self.config.read_text(encoding="utf-8"))
        (self.root / "target.txt").write_text("x", encoding="utf-8")
        self.test_adapter = GenericStdinAdapter(adapter_name="opencode")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_resource_selector_resolves_underlying_executor_and_preserves_resource_id(self) -> None:
        prepared = prepare_agent_run(
            executor_id="opencode-free",
            repo_raw="workspace-root",
            workdir_raw=str(self.root),
            prompt_raw="prompt",
            target_raws=["target.txt"],
            workspace_root=self.root,
            workspace_config_file=self.config,
            workspace_config=self.workspace_config,
            root_repo="softos-agentic",
        )
        executor, _repo, _workdir, _targets, _prompt = prepared
        self.assertEqual("opencode", executor.executor_id)
        self.assertEqual(str(self.fake), executor.executable)
        self.assertEqual("opencode-free", prepared.resource_id)
        self.assertIsNotNone(prepared.resource)
        assert prepared.resource is not None
        self.assertEqual("dynamic_free", prepared.resource.model_resolution)

    def test_legacy_executor_selector_still_works_without_resource_id(self) -> None:
        prepared = prepare_agent_run(
            executor_id="codex",
            repo_raw="workspace-root",
            workdir_raw=str(self.root),
            prompt_raw="prompt",
            target_raws=["target.txt"],
            workspace_root=self.root,
            workspace_config_file=self.config,
            workspace_config=self.workspace_config,
            root_repo="softos-agentic",
        )
        self.assertEqual("codex", prepared.executor.executor_id)
        self.assertIsNone(prepared.resource_id)
        self.assertIsNone(prepared.resource)

    def test_opencode_local_resource_uses_local_executor_without_model_overlay(self) -> None:
        prepared = prepare_agent_run(
            executor_id="opencode-local",
            repo_raw="workspace-root",
            workdir_raw=str(self.root),
            prompt_raw="prompt",
            target_raws=["target.txt"],
            workspace_root=self.root,
            workspace_config_file=self.config,
            workspace_config=self.workspace_config,
            root_repo="softos-agentic",
        )
        self.assertEqual("opencode-local", prepared.executor.executor_id)
        self.assertEqual("opencode-local", prepared.resource_id)

        captured: dict[str, object] = {}

        def fake_run(**kwargs: object) -> object:
            captured.update(kwargs)
            return subprocess.CompletedProcess(args=kwargs["args"], returncode=0, stdout=b"", stderr=b"")

        with mock.patch(
            "flowctl.agent_process_execution.resolve_adapter",
            return_value=self.test_adapter,
        ):
            exit_code, metadata = run_agent_process(
                executor=prepared.executor,
                repo=prepared.repo,
                workspace_root=self.root,
                workdir=prepared.workdir,
                targets=prepared.targets,
                prompt=prepared.prompt,
                shutil_which=lambda _: str(self.fake),
                subprocess_run=fake_run,
                resource_id=prepared.resource_id,
                resource=prepared.resource,
                inherited_env={
                    "PATH": "/usr/bin",
                    OPENCODE_CONFIG_CONTENT_ENV: json.dumps(
                        {"default_agent": "softos-local-worker"}
                    ),
                },
            )
        self.assertEqual(0, exit_code)
        self.assertEqual("opencode-local", metadata.resource_id)
        # Local keeps true inheritance: no env= kwarg when overlay is empty.
        self.assertNotIn("env", captured)

    def test_free_resolved_model_reaches_subprocess_overlay(self) -> None:
        prepared = prepare_agent_run(
            executor_id="opencode-free",
            repo_raw="workspace-root",
            workdir_raw=str(self.root),
            prompt_raw="prompt",
            target_raws=["target.txt"],
            workspace_root=self.root,
            workspace_config_file=self.config,
            workspace_config=self.workspace_config,
            root_repo="softos-agentic",
        )
        captured: dict[str, object] = {}

        def fake_run(**kwargs: object) -> object:
            captured.update(kwargs)
            return subprocess.CompletedProcess(args=kwargs["args"], returncode=0, stdout=b"", stderr=b"")

        with mock.patch(
            "flowctl.agent_process_execution.resolve_adapter",
            return_value=self.test_adapter,
        ):
            exit_code, metadata = run_agent_process(
                executor=prepared.executor,
                repo=prepared.repo,
                workspace_root=self.root,
                workdir=prepared.workdir,
                targets=prepared.targets,
                prompt=prepared.prompt,
                shutil_which=lambda _: str(self.fake),
                subprocess_run=fake_run,
                resource_id=prepared.resource_id,
                resource=prepared.resource,
                discover_free=lambda: ["zeta-free", "alpha-free"],
                inherited_env={
                    "PATH": "/usr/bin",
                    "SAFE_FLAG": "1",
                    OPENCODE_CONFIG_CONTENT_ENV: json.dumps(
                        {"default_agent": "softos-local-worker"}
                    ),
                    "OPENCODE_CONFIG": "/tmp/local-opencode.json",
                },
            )
        self.assertEqual(0, exit_code)
        self.assertEqual("opencode-free", metadata.resource_id)
        env = captured["env"]
        assert isinstance(env, dict)
        self.assertEqual("1", env["SAFE_FLAG"])
        self.assertEqual("/usr/bin", env["PATH"])
        self.assertNotIn("OPENCODE_CONFIG", env)
        content = json.loads(env[OPENCODE_CONFIG_CONTENT_ENV])
        self.assertEqual({"model": "alpha-free"}, content)
        self.assertNotIn("default_agent", content)
        argv = list(captured["args"])
        self.assertNotIn("--model", argv)
        self.assertNotIn("--provider", argv)
        self.assertNotIn("--resource", argv)

    def test_go_auth_unconfigured_cannot_launch(self) -> None:
        prepared = prepare_agent_run(
            executor_id="opencode-go",
            repo_raw="workspace-root",
            workdir_raw=str(self.root),
            prompt_raw="prompt",
            target_raws=["target.txt"],
            workspace_root=self.root,
            workspace_config_file=self.config,
            workspace_config=self.workspace_config,
            root_repo="softos-agentic",
        )
        with mock.patch(
            "flowctl.agent_process_execution.resolve_adapter",
            return_value=self.test_adapter,
        ):
            with mock.patch(
                "flowctl.agent_process_execution.probe_opencode_auth",
                return_value="AUTH_UNCONFIGURED",
            ) as probe_auth:
                with self.assertRaisesRegex(AgentRunError, "AUTH_UNCONFIGURED"):
                    run_agent_process(
                        executor=prepared.executor,
                        repo=prepared.repo,
                        workspace_root=self.root,
                        workdir=prepared.workdir,
                        targets=prepared.targets,
                        prompt=prepared.prompt,
                        shutil_which=lambda _: str(self.fake),
                        subprocess_run=subprocess.run,
                        resource_id=prepared.resource_id,
                        resource=prepared.resource,
                        discover_go=lambda: ["go-model-b", "go-model-a"],
                    )
        probe_auth.assert_called_once()

    def test_go_provider_available_and_models_present_launches_without_explicit_auth_evidence(self) -> None:
        prepared = prepare_agent_run(
            executor_id="opencode-go",
            repo_raw="workspace-root",
            workdir_raw=str(self.root),
            prompt_raw="prompt",
            target_raws=["target.txt"],
            workspace_root=self.root,
            workspace_config_file=self.config,
            workspace_config=self.workspace_config,
            root_repo="softos-agentic",
        )
        captured: dict[str, object] = {}

        def fake_run(**kwargs: object) -> object:
            captured.update(kwargs)
            return subprocess.CompletedProcess(args=kwargs["args"], returncode=0, stdout=b"", stderr=b"")

        with mock.patch(
            "flowctl.agent_process_execution.resolve_adapter",
            return_value=self.test_adapter,
        ):
            with mock.patch(
                "flowctl.agent_process_execution.probe_opencode_auth",
                return_value="AVAILABLE",
            ) as probe_auth:
                exit_code, metadata = run_agent_process(
                    executor=prepared.executor,
                    repo=prepared.repo,
                    workspace_root=self.root,
                    workdir=prepared.workdir,
                    targets=prepared.targets,
                    prompt=prepared.prompt,
                    shutil_which=lambda _: str(self.fake),
                    subprocess_run=fake_run,
                    resource_id=prepared.resource_id,
                    resource=prepared.resource,
                    discover_go=lambda: ["go-model-b", "go-model-a"],
                    inherited_env={
                        "PATH": "/usr/bin",
                        OPENCODE_CONFIG_CONTENT_ENV: json.dumps(
                            {"default_agent": "softos-local-worker"}
                        ),
                    },
                )
        self.assertEqual(0, exit_code)
        self.assertEqual("opencode-go", metadata.resource_id)
        probe_auth.assert_called_once()
        env = captured["env"]
        assert isinstance(env, dict)
        content = json.loads(env[OPENCODE_CONFIG_CONTENT_ENV])
        self.assertEqual({"model": "go-model-a"}, content)
        self.assertNotIn("default_agent", content)

    def test_go_provider_available_but_no_candidates_is_model_unavailable(self) -> None:
        prepared = prepare_agent_run(
            executor_id="opencode-go",
            repo_raw="workspace-root",
            workdir_raw=str(self.root),
            prompt_raw="prompt",
            target_raws=["target.txt"],
            workspace_root=self.root,
            workspace_config_file=self.config,
            workspace_config=self.workspace_config,
            root_repo="softos-agentic",
        )
        with mock.patch(
            "flowctl.agent_process_execution.probe_opencode_auth",
            return_value="AVAILABLE",
        ) as probe_auth:
            with mock.patch(
                "flowctl.agent_process_execution.resolve_adapter",
                return_value=self.test_adapter,
            ):
                with self.assertRaisesRegex(AgentRunError, "MODEL_UNAVAILABLE"):
                    run_agent_process(
                        executor=prepared.executor,
                        repo=prepared.repo,
                        workspace_root=self.root,
                        workdir=prepared.workdir,
                        targets=prepared.targets,
                        prompt=prepared.prompt,
                        shutil_which=lambda _: str(self.fake),
                        subprocess_run=subprocess.run,
                        resource_id=prepared.resource_id,
                        resource=prepared.resource,
                        discover_go=lambda: [],
                    )
        probe_auth.assert_called_once()

    def test_overlay_merge_preserves_inherited_env_and_never_replaces_wholesale(self) -> None:
        inherited = {"PATH": "/bin", "SAFE": "yes", "OPENCODE_CONFIG": "/local.json"}
        overlay = {OPENCODE_CONFIG_CONTENT_ENV: json.dumps({"model": "alpha-free"})}
        merged = merge_process_environment(
            inherited,
            overlay,
            scrub_keys=frozenset({"OPENCODE_CONFIG", OPENCODE_CONFIG_CONTENT_ENV}),
        )
        self.assertEqual("/bin", merged["PATH"])
        self.assertEqual("yes", merged["SAFE"])
        self.assertNotIn("OPENCODE_CONFIG", merged)
        self.assertEqual({"model": "alpha-free"}, json.loads(merged[OPENCODE_CONFIG_CONTENT_ENV]))
        # Original inherited mapping is untouched.
        self.assertEqual("/local.json", inherited["OPENCODE_CONFIG"])

    def test_overlay_rejects_credentials_and_provider_payloads(self) -> None:
        with self.assertRaisesRegex(AgentRunError, "prohibida"):
            validate_process_env_overlay({"OPENAI_API_KEY": "sk-secret"})
        with self.assertRaisesRegex(AgentRunError, "prohibido"):
            validate_process_env_overlay(
                {
                    OPENCODE_CONFIG_CONTENT_ENV: json.dumps(
                        {"model": "alpha-free", "provider": {"apiKey": "secret"}}
                    )
                }
            )
        with self.assertRaisesRegex(AgentRunError, "prohibido"):
            validate_process_env_overlay(
                {
                    OPENCODE_CONFIG_CONTENT_ENV: json.dumps(
                        {"model": "alpha-free", "token": "abc"}
                    )
                }
            )

    def test_free_and_go_share_executor_but_metadata_keeps_distinct_resource_ids(self) -> None:
        free = prepare_agent_run(
            executor_id="opencode-free",
            repo_raw="workspace-root",
            workdir_raw=str(self.root),
            prompt_raw="prompt",
            target_raws=["target.txt"],
            workspace_root=self.root,
            workspace_config_file=self.config,
            workspace_config=self.workspace_config,
            root_repo="softos-agentic",
        )
        go = prepare_agent_run(
            executor_id="opencode-go",
            repo_raw="workspace-root",
            workdir_raw=str(self.root),
            prompt_raw="prompt",
            target_raws=["target.txt"],
            workspace_root=self.root,
            workspace_config_file=self.config,
            workspace_config=self.workspace_config,
            root_repo="softos-agentic",
        )
        self.assertEqual(free.executor.executor_id, go.executor.executor_id)
        self.assertEqual("opencode-free", free.resource_id)
        self.assertEqual("opencode-go", go.resource_id)

    def test_production_default_discovery_used_when_hooks_omitted(self) -> None:
        prepared = prepare_agent_run(
            executor_id="opencode-free",
            repo_raw="workspace-root",
            workdir_raw=str(self.root),
            prompt_raw="prompt",
            target_raws=["target.txt"],
            workspace_root=self.root,
            workspace_config_file=self.config,
            workspace_config=self.workspace_config,
            root_repo="softos-agentic",
        )
        captured: dict[str, object] = {}

        def fake_run(**kwargs: object) -> object:
            captured.update(kwargs)
            return subprocess.CompletedProcess(args=kwargs["args"], returncode=0, stdout=b"", stderr=b"")

        with mock.patch(
            "flowctl.agent_process_execution.probe_opencode_models",
            return_value=["zeta-free", "alpha-free"],
        ) as probe:
            with mock.patch(
                "flowctl.agent_process_execution.resolve_adapter",
                return_value=self.test_adapter,
            ):
                exit_code, metadata = run_agent_process(
                    executor=prepared.executor,
                    repo=prepared.repo,
                    workspace_root=self.root,
                    workdir=prepared.workdir,
                    targets=prepared.targets,
                    prompt=prepared.prompt,
                    shutil_which=lambda _: str(self.fake),
                    subprocess_run=fake_run,
                    resource_id=prepared.resource_id,
                    resource=prepared.resource,
                    inherited_env={"PATH": "/usr/bin", "SAFE_FLAG": "1"},
                )
        self.assertEqual(0, exit_code)
        self.assertEqual("opencode-free", metadata.resource_id)
        probe.assert_called()
        env = captured["env"]
        assert isinstance(env, dict)
        self.assertEqual("1", env["SAFE_FLAG"])
        self.assertEqual({"model": "alpha-free"}, json.loads(env[OPENCODE_CONFIG_CONTENT_ENV]))
        argv = list(captured["args"])
        self.assertNotIn("--model", argv)
        self.assertNotIn("--provider", argv)

    def test_injected_discovery_still_overrides_production_default(self) -> None:
        prepared = prepare_agent_run(
            executor_id="opencode-free",
            repo_raw="workspace-root",
            workdir_raw=str(self.root),
            prompt_raw="prompt",
            target_raws=["target.txt"],
            workspace_root=self.root,
            workspace_config_file=self.config,
            workspace_config=self.workspace_config,
            root_repo="softos-agentic",
        )
        captured: dict[str, object] = {}

        def fake_run(**kwargs: object) -> object:
            captured.update(kwargs)
            return subprocess.CompletedProcess(args=kwargs["args"], returncode=0, stdout=b"", stderr=b"")

        with mock.patch(
            "flowctl.agent_process_execution.probe_opencode_models",
            return_value=["should-not-use-free"],
        ) as probe:
            with mock.patch(
                "flowctl.agent_process_execution.resolve_adapter",
                return_value=self.test_adapter,
            ):
                exit_code, _metadata = run_agent_process(
                    executor=prepared.executor,
                    repo=prepared.repo,
                    workspace_root=self.root,
                    workdir=prepared.workdir,
                    targets=prepared.targets,
                    prompt=prepared.prompt,
                    shutil_which=lambda _: str(self.fake),
                    subprocess_run=fake_run,
                    resource_id=prepared.resource_id,
                    resource=prepared.resource,
                    discover_free=lambda: ["injected-z-free", "injected-a-free"],
                    inherited_env={"PATH": "/usr/bin"},
                )
        self.assertEqual(0, exit_code)
        probe.assert_not_called()
        env = captured["env"]
        assert isinstance(env, dict)
        self.assertEqual({"model": "injected-a-free"}, json.loads(env[OPENCODE_CONFIG_CONTENT_ENV]))

    def test_go_without_auth_stays_unconfigured_even_with_default_discovery(self) -> None:
        prepared = prepare_agent_run(
            executor_id="opencode-go",
            repo_raw="workspace-root",
            workdir_raw=str(self.root),
            prompt_raw="prompt",
            target_raws=["target.txt"],
            workspace_root=self.root,
            workspace_config_file=self.config,
            workspace_config=self.workspace_config,
            root_repo="softos-agentic",
        )
        with mock.patch(
            "flowctl.agent_process_execution.probe_opencode_models",
            return_value=["go-model-b", "go-model-a"],
        ) as probe:
            with mock.patch(
                "flowctl.agent_process_execution.resolve_adapter",
                return_value=self.test_adapter,
            ):
                with mock.patch(
                    "flowctl.agent_process_execution.probe_opencode_auth",
                    return_value="AUTH_UNCONFIGURED",
                ) as probe_auth:
                    with self.assertRaisesRegex(AgentRunError, "AUTH_UNCONFIGURED"):
                        run_agent_process(
                            executor=prepared.executor,
                            repo=prepared.repo,
                            workspace_root=self.root,
                            workdir=prepared.workdir,
                            targets=prepared.targets,
                            prompt=prepared.prompt,
                            shutil_which=lambda _: str(self.fake),
                            subprocess_run=subprocess.run,
                            resource_id=prepared.resource_id,
                            resource=prepared.resource,
                            auth_evidence=None,
                        )
        probe_auth.assert_called_once()
        probe.assert_not_called()

    def test_authenticated_go_uses_default_discovery_and_overlay(self) -> None:
        prepared = prepare_agent_run(
            executor_id="opencode-go",
            repo_raw="workspace-root",
            workdir_raw=str(self.root),
            prompt_raw="prompt",
            target_raws=["target.txt"],
            workspace_root=self.root,
            workspace_config_file=self.config,
            workspace_config=self.workspace_config,
            root_repo="softos-agentic",
        )
        captured: dict[str, object] = {}

        def fake_run(**kwargs: object) -> object:
            captured.update(kwargs)
            return subprocess.CompletedProcess(args=kwargs["args"], returncode=0, stdout=b"", stderr=b"")

        with mock.patch(
            "flowctl.agent_process_execution.probe_opencode_models",
            return_value=["go-model-b", "go-model-a"],
        ):
            with mock.patch(
                "flowctl.agent_process_execution.resolve_adapter",
                return_value=self.test_adapter,
            ):
                exit_code, metadata = run_agent_process(
                    executor=prepared.executor,
                    repo=prepared.repo,
                    workspace_root=self.root,
                    workdir=prepared.workdir,
                    targets=prepared.targets,
                    prompt=prepared.prompt,
                    shutil_which=lambda _: str(self.fake),
                    subprocess_run=fake_run,
                    resource_id=prepared.resource_id,
                    resource=prepared.resource,
                    auth_evidence="AVAILABLE",
                    inherited_env={
                        "PATH": "/usr/bin",
                        OPENCODE_CONFIG_CONTENT_ENV: json.dumps(
                            {"default_agent": "softos-local-worker"}
                        ),
                        "OPENCODE_CONFIG": "/tmp/local-opencode.json",
                    },
                )
        self.assertEqual(0, exit_code)
        self.assertEqual("opencode-go", metadata.resource_id)
        env = captured["env"]
        assert isinstance(env, dict)
        self.assertEqual("/usr/bin", env["PATH"])
        self.assertNotIn("OPENCODE_CONFIG", env)
        self.assertEqual({"model": "go-model-a"}, json.loads(env[OPENCODE_CONFIG_CONTENT_ENV]))
        self.assertNotIn("default_agent", json.loads(env[OPENCODE_CONFIG_CONTENT_ENV]))

    def test_default_discovery_failure_maps_to_normalized_failure(self) -> None:
        prepared = prepare_agent_run(
            executor_id="opencode-free",
            repo_raw="workspace-root",
            workdir_raw=str(self.root),
            prompt_raw="prompt",
            target_raws=["target.txt"],
            workspace_root=self.root,
            workspace_config_file=self.config,
            workspace_config=self.workspace_config,
            root_repo="softos-agentic",
        )
        with mock.patch(
            "flowctl.agent_process_execution.probe_opencode_models",
            side_effect=RuntimeError("probe_boom"),
        ):
            with mock.patch(
                "flowctl.agent_process_execution.resolve_adapter",
                return_value=self.test_adapter,
            ):
                with self.assertRaisesRegex(AgentRunError, "discovery_error:RuntimeError|UNKNOWN"):
                    run_agent_process(
                        executor=prepared.executor,
                        repo=prepared.repo,
                        workspace_root=self.root,
                        workdir=prepared.workdir,
                        targets=prepared.targets,
                        prompt=prepared.prompt,
                        shutil_which=lambda _: str(self.fake),
                        subprocess_run=subprocess.run,
                        resource_id=prepared.resource_id,
                        resource=prepared.resource,
                    )

    def test_command_agent_run_production_path_resolves_free_without_hooks(self) -> None:
        captured: dict[str, object] = {}

        def fake_run(**kwargs: object) -> object:
            captured.update(kwargs)
            return subprocess.CompletedProcess(args=kwargs["args"], returncode=0, stdout=b"", stderr=b"")

        with mock.patch(
            "flowctl.agent_process_execution.probe_opencode_models",
            return_value=["zeta-free", "alpha-free"],
        ):
            with mock.patch(
                "flowctl.agent_process_execution.resolve_adapter",
                return_value=self.test_adapter,
            ):
                rc = command_agent_run(
                    argparse_namespace(
                        executor="opencode-free",
                        repo="workspace-root",
                        workdir=str(self.root),
                        prompt="prompt",
                        target=["target.txt"],
                    ),
                    workspace_root=self.root,
                    workspace_config_file=self.config,
                    workspace_config=self.workspace_config,
                    worktree_root=self.root / ".worktrees",
                    root_repo="softos-agentic",
                    repo_names=["softos-agentic"],
                    shutil_which=lambda _: str(self.fake),
                    subprocess_run=fake_run,
                )
        self.assertEqual(0, rc)
        env = captured["env"]
        assert isinstance(env, dict)
        self.assertEqual({"model": "alpha-free"}, json.loads(env[OPENCODE_CONFIG_CONTENT_ENV]))

    def test_probe_opencode_models_extracts_ids_without_persisting_payload(self) -> None:
        def fake_run(*args: object, **kwargs: object) -> object:
            return subprocess.CompletedProcess(
                args=["opencode", "models"],
                returncode=0,
                stdout="zeta-free\nalpha-free\npaid-pro\n",
                stderr="",
            )

        models = probe_opencode_models(subprocess_run=fake_run)
        self.assertEqual(["zeta-free", "alpha-free", "paid-pro"], models)

        def failing_run(*args: object, **kwargs: object) -> object:
            return subprocess.CompletedProcess(
                args=["opencode", "models"],
                returncode=2,
                stdout="",
                stderr="boom",
            )

        with self.assertRaisesRegex(RuntimeError, "opencode_models_probe_failed"):
            probe_opencode_models(subprocess_run=failing_run)

        prepared = prepare_agent_run(
            executor_id="opencode-free",
            repo_raw="workspace-root",
            workdir_raw=str(self.root),
            prompt_raw="prompt",
            target_raws=["target.txt"],
            workspace_root=self.root,
            workspace_config_file=self.config,
            workspace_config=self.workspace_config,
            root_repo="softos-agentic",
        )
        assert prepared.resource is not None
        model_id = resolve_resource_model(
            prepared.resource,
            default_discover=lambda: ["zeta-free", "alpha-free"],
        )
        self.assertEqual("alpha-free", model_id)


if __name__ == "__main__":
    unittest.main()
