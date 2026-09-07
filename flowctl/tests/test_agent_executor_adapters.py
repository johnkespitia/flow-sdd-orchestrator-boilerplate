from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from flowctl.agent_executor_adapters import (
    EXECUTION_CONTRACT_BEGIN,
    EXECUTION_CONTRACT_END,
    AgentRunRequest,
    CodexAdapter,
    CursorAdapter,
    OpenCodeAdapter,
    StaticArgvValidationError,
    build_delivered_prompt,
    build_execution_contract,
    resolve_adapter,
    validate_static_argv,
)
from flowctl.agent_executors import AgentExecutor, command_agent_run
from flowctl.agent_process_execution import run_agent_process


def _sample_request(
    *,
    adapter: str,
    executable: str,
    argv: tuple[str, ...] = (),
    user_prompt: str = "operator prompt",
) -> AgentRunRequest:
    executor = AgentExecutor(
        executor_id=f"test-{adapter}",
        adapter=adapter,
        executable=executable,
        argv=argv,
    )
    contract_body = build_execution_contract(
        request=AgentRunRequest(
            executor=executor,
            repo="softos-agentic",
            workspace_root="/workspace",
            workdir="/workspace/.worktrees/demo",
            targets=("a.txt", "b.txt"),
            user_prompt=user_prompt,
            contract_body="",
        )
    )
    return AgentRunRequest(
        executor=executor,
        repo="softos-agentic",
        workspace_root="/workspace",
        workdir="/workspace/.worktrees/demo",
        targets=("a.txt", "b.txt"),
        user_prompt=user_prompt,
        contract_body=contract_body,
    )


def _write_config(root: Path, *, agents: object) -> Path:
    payload: dict[str, object] = {
        "project": {"display_name": "Test", "root_repo": "softos-agentic"},
        "repos": {"softos-agentic": {"path": ".", "kind": "root"}},
        "agents": agents,
    }
    path = root / "workspace.config.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _expected_delivered_prompt(*, harness: dict[str, object]) -> str:
    executor = AgentExecutor(
        executor_id=str(harness["executor_id"]),
        adapter=str(harness["adapter"]),
        executable=str(harness["executable"]),
        argv=tuple(harness.get("static_argv", [])),
    )
    contract_body = build_execution_contract(
        request=AgentRunRequest(
            executor=executor,
            repo="softos-agentic",
            workspace_root=str(harness["workspace_root"]),
            workdir=str(harness["workdir"]),
            targets=tuple(harness["targets"]),
            user_prompt=str(harness["user_prompt"]),
            contract_body="",
        )
    )
    return f"{contract_body}\n\n{harness['user_prompt']}"


def _write_harness_fake_cli(path: Path, *, harness: dict[str, object]) -> None:
    """Fake CLI that validates argv shape, cwd, prompt delivery, and exit code."""
    script = f'''#!/usr/bin/env python3
import os
import sys

EXECUTION_CONTRACT_BEGIN = {EXECUTION_CONTRACT_BEGIN!r}
EXECUTION_CONTRACT_END = {EXECUTION_CONTRACT_END!r}

harness = {json.dumps(harness)}
static_argv = harness.get("static_argv", [])
exit_code = int(harness.get("exit_code", 0))
expected_cwd = harness.get("expected_cwd")
user_prompt = harness["user_prompt"]
expected_prompt = harness["expected_prompt"]

if expected_cwd is not None and os.getcwd() != expected_cwd:
    sys.stderr.write("CWD_MISMATCH")
    raise SystemExit(99)

if harness["name"] == "codex":
    expected_tail = ["exec", "--approve-for-me", "--", expected_prompt]
    expected_prefix = [harness["executable"], *static_argv]
elif harness["name"] == "cursor":
    expected_tail = ["--trust", "-p", "--", expected_prompt]
    expected_prefix = [harness["executable"], *static_argv]
elif harness["name"] == "opencode":
    expected_tail = ["run", "--auto", "--dir", harness["workdir"], "--", expected_prompt]
    expected_prefix = [harness["executable"], *static_argv]
else:
    sys.stderr.write("UNKNOWN_HARNESS")
    raise SystemExit(98)

expected = expected_prefix + expected_tail
if sys.argv != expected:
    sys.stderr.write("ARGV_MISMATCH:" + repr(sys.argv))
    raise SystemExit(97)

delimiter_index = sys.argv.index("--")
if delimiter_index != len(sys.argv) - 2:
    sys.stderr.write("DELIMITER_POSITION")
    raise SystemExit(92)
prompt = sys.argv[-1]

if prompt != expected_prompt:
    sys.stderr.write("PROMPT_NOT_EXACT")
    raise SystemExit(91)

if prompt.count(user_prompt) != 1:
    sys.stderr.write("PROMPT_MUTATED")
    raise SystemExit(94)

if not prompt.startswith(EXECUTION_CONTRACT_BEGIN):
    sys.stderr.write("CONTRACT_BEGIN_MISSING")
    raise SystemExit(96)

if EXECUTION_CONTRACT_END not in prompt:
    sys.stderr.write("CONTRACT_END_MISSING")
    raise SystemExit(95)

separator = "\\n\\n"
if not prompt.endswith(user_prompt):
    sys.stderr.write("USER_PROMPT_SUFFIX_MISMATCH")
    raise SystemExit(90)

contract_prefix = prompt[: -len(user_prompt)]
if not contract_prefix.endswith(separator):
    sys.stderr.write("SEPARATOR_MISMATCH")
    raise SystemExit(87)

for forbidden in ("--model", "--provider", "--full-auto"):
    if forbidden in sys.argv:
        sys.stderr.write("FORBIDDEN_FLAG")
        raise SystemExit(93)

sys.stdout.write("FAKE_STDOUT")
sys.stderr.write("FAKE_STDERR")
raise SystemExit(exit_code)
'''
    path.write_text(script, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class ExecutionContractTests(unittest.TestCase):
    def test_repo_runtime_places_workdir_before_repo(self) -> None:
        executor = AgentExecutor(
            executor_id="cursor",
            adapter="cursor",
            executable="agent",
            argv=(),
        )
        contract = build_execution_contract(
            request=AgentRunRequest(
                executor=executor,
                repo="softos-agentic",
                workspace_root="/workspace",
                workdir="/workspace/.worktrees/demo",
                targets=("flowctl/example.py",),
                user_prompt="do work",
                contract_body="",
            )
        )
        self.assertIn(
            "python3 ./flow repo exec --workdir /workspace/.worktrees/demo softos-agentic -- <command>",
            contract,
        )
        self.assertNotIn(
            "python3 ./flow repo exec softos-agentic --workdir /workspace/.worktrees/demo -- <command>",
            contract,
        )


class AdapterContractTests(unittest.TestCase):
    def test_codex_argv_shape_without_static_argv(self) -> None:
        request = _sample_request(adapter="codex", executable="codex")
        invocation = CodexAdapter().build_invocation(request)
        delivered_prompt = build_delivered_prompt(request)
        self.assertIsNone(invocation.stdin)
        self.assertEqual(
            ("codex", "exec", "--approve-for-me", "--", delivered_prompt),
            invocation.argv,
        )

    def test_codex_argv_forwards_process_local_model_and_sandbox(self) -> None:
        request = _sample_request(adapter="codex", executable="codex")
        request = AgentRunRequest(
            **{**request.__dict__, "model": "gpt-6-astra", "sandbox": "workspace-write"}
        )
        invocation = CodexAdapter().build_invocation(request)
        delivered_prompt = build_delivered_prompt(request)
        self.assertEqual(
            (
                "codex",
                "exec",
                "-m",
                "gpt-6-astra",
                "-s",
                "workspace-write",
                "--",
                delivered_prompt,
            ),
            invocation.argv,
        )

    def test_codex_rejects_invalid_process_local_sandbox(self) -> None:
        request = _sample_request(adapter="codex", executable="codex")
        request = AgentRunRequest(**{**request.__dict__, "sandbox": "invalid"})
        with self.assertRaisesRegex(ValueError, "sandbox Codex"):
            CodexAdapter().build_invocation(request)

    def test_cursor_argv_shape_without_static_argv(self) -> None:
        request = _sample_request(adapter="cursor", executable="agent")
        invocation = CursorAdapter().build_invocation(request)
        delivered_prompt = build_delivered_prompt(request)
        self.assertIsNone(invocation.stdin)
        self.assertEqual(
            ("agent", "--trust", "-p", "--", delivered_prompt),
            invocation.argv,
        )

    def test_opencode_argv_shape_without_static_argv(self) -> None:
        request = _sample_request(adapter="opencode", executable="opencode")
        invocation = OpenCodeAdapter().build_invocation(request)
        delivered_prompt = build_delivered_prompt(request)
        self.assertIsNone(invocation.stdin)
        self.assertEqual(
            ("opencode", "run", "--auto", "--dir", request.workdir, "--", delivered_prompt),
            invocation.argv,
        )

    def test_opencode_argv_includes_assigned_workdir_before_prompt_delimiter(self) -> None:
        request = _sample_request(adapter="opencode", executable="opencode")
        invocation = OpenCodeAdapter().build_invocation(request)
        delivered_prompt = build_delivered_prompt(request)
        dir_index = invocation.argv.index("--dir")
        self.assertEqual(request.workdir, invocation.argv[dir_index + 1])
        self.assertEqual("--", invocation.argv[-2])
        self.assertEqual(delivered_prompt, invocation.argv[-1])

    def test_empty_static_argv_is_canonical_for_all_adapters(self) -> None:
        for adapter_name, executable in (
            ("codex", "codex"),
            ("cursor", "agent"),
            ("opencode", "opencode"),
        ):
            with self.subTest(adapter=adapter_name):
                request = _sample_request(adapter=adapter_name, executable=executable, argv=())
                invocation = resolve_adapter(adapter_name).build_invocation(request)
                self.assertEqual((), request.executor.argv)
                self.assertEqual(1, sum(1 for item in invocation.argv if item == build_delivered_prompt(request)))

    def test_option_shaped_prompt_uses_safe_transport(self) -> None:
        user_prompt = "operator prompt"
        request = _sample_request(adapter="codex", executable="codex", user_prompt=user_prompt)
        delivered_prompt = build_delivered_prompt(request)
        self.assertTrue(delivered_prompt.startswith("---"))

        codex = CodexAdapter().build_invocation(request)
        self.assertEqual("--", codex.argv[-2])
        self.assertEqual(delivered_prompt, codex.argv[-1])

        opencode = OpenCodeAdapter().build_invocation(request)
        self.assertEqual("--", opencode.argv[-2])
        self.assertEqual(delivered_prompt, opencode.argv[-1])

        cursor = CursorAdapter().build_invocation(request)
        self.assertEqual("--", cursor.argv[-2])
        self.assertEqual(delivered_prompt, cursor.argv[-1])

    def test_delivered_prompt_exact_contract_plus_user_prompt(self) -> None:
        request = _sample_request(adapter="codex", executable="codex", user_prompt="ship it")
        delivered = build_delivered_prompt(request)
        self.assertEqual(f"{request.contract_body}\n\n{request.user_prompt}", delivered)
        self.assertTrue(delivered.startswith(EXECUTION_CONTRACT_BEGIN))
        self.assertIn(EXECUTION_CONTRACT_END, delivered)
        self.assertTrue(delivered.endswith(request.user_prompt))

    def test_prompt_is_exactly_one_discrete_argv_element(self) -> None:
        user_prompt = "line one\nline two"
        for adapter_name in ("codex", "cursor", "opencode"):
            with self.subTest(adapter=adapter_name):
                request = _sample_request(
                    adapter=adapter_name,
                    executable=adapter_name,
                    user_prompt=user_prompt,
                )
                delivered = build_delivered_prompt(request)
                invocation = resolve_adapter(adapter_name).build_invocation(request)
                self.assertEqual(1, sum(1 for item in invocation.argv if item == delivered))
                self.assertEqual(delivered, invocation.argv[-1])

    def test_identical_logical_contract_reaches_all_three_adapters(self) -> None:
        request = _sample_request(adapter="codex", executable="codex")
        delivered = build_delivered_prompt(request)
        prompts = {
            adapter_name: resolve_adapter(adapter_name).build_invocation(request).argv[-1]
            for adapter_name in ("codex", "cursor", "opencode")
        }
        self.assertEqual({delivered}, set(prompts.values()))

    def test_no_model_or_provider_arguments_introduced(self) -> None:
        forbidden = ("--model", "--provider", "--full-auto", "-m", "gpt-4", "claude")
        for adapter_name in ("codex", "cursor", "opencode"):
            with self.subTest(adapter=adapter_name):
                request = _sample_request(adapter=adapter_name, executable=adapter_name)
                invocation = resolve_adapter(adapter_name).build_invocation(request)
                for token in forbidden:
                    self.assertNotIn(token, invocation.argv)

    def test_unknown_adapter_is_deterministic(self) -> None:
        with self.assertRaisesRegex(ValueError, "Adapter no soportado: `missing`"):
            resolve_adapter("missing")

    @staticmethod
    def _unsafe_static_argv_cases() -> list[tuple[str, tuple[str, ...]]]:
        shared = (
            ("--help",),
            ("-h",),
            ("--version",),
            ("--",),
            ("--model", "gpt-4"),
            ("--provider", "openai"),
            ("--full-auto",),
            ("positional",),
        )
        return [
            ("codex", ("exec",)),
            ("codex", ("run",)),
            ("codex", ("--approve-for-me",)),
            ("codex", ("--verbose",)),
            ("codex", ("--profile", "test")),
            *[(adapter, case) for case in shared for adapter in ("codex", "cursor", "opencode")],
            ("cursor", ("--trust",)),
            ("cursor", ("-p", "hack")),
            ("cursor", ("exec",)),
            ("cursor", ("run",)),
            ("opencode", ("run",)),
            ("opencode", ("exec",)),
            ("opencode", ("--auto",)),
            ("opencode", ("--dir", "/other/worktree")),
            ("opencode", ("--dir",)),
        ]

    def test_unsafe_static_argv_is_rejected_before_launch(self) -> None:
        for adapter_name, static_argv in self._unsafe_static_argv_cases():
            with self.subTest(adapter=adapter_name, static_argv=static_argv):
                request = _sample_request(
                    adapter=adapter_name,
                    executable=adapter_name,
                    argv=static_argv,
                )
                with self.assertRaises(StaticArgvValidationError):
                    resolve_adapter(adapter_name).build_invocation(request)

    def test_static_argv_validation_error_does_not_echo_secret_values(self) -> None:
        secret_argv = "SUPER_SECRET_ARGV_TOKEN"
        with self.assertRaises(StaticArgvValidationError) as ctx:
            validate_static_argv("codex", (secret_argv,))
        diagnostic = str(ctx.exception)
        self.assertIn("argv estatico no permitido", diagnostic)
        self.assertNotIn(secret_argv, diagnostic)


class FakeCliIntegrationTests(unittest.TestCase):
    def _run_harness(
        self,
        *,
        harness_name: str,
        adapter: str,
        executable_name: str,
        executor_id: str,
        exit_code: int = 0,
        static_argv: list[str] | None = None,
        user_prompt: str = "do the thing",
    ) -> tuple[int, dict[str, bytes]]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = root / executable_name
            workdir = str(root.resolve())
            harness = {
                "name": harness_name,
                "adapter": adapter,
                "executable": str(fake),
                "executor_id": executor_id,
                "static_argv": static_argv or [],
                "expected_cwd": workdir,
                "workspace_root": workdir,
                "workdir": workdir,
                "targets": ["target.txt"],
                "user_prompt": user_prompt,
                "exit_code": exit_code,
            }
            harness["expected_prompt"] = _expected_delivered_prompt(harness=harness)
            _write_harness_fake_cli(fake, harness=harness)
            config = _write_config(
                root,
                agents={
                    "schema_version": 1,
                    "executors": {
                        executor_id: {
                            "adapter": adapter,
                            "executable": str(fake),
                            "argv": static_argv or [],
                        },
                    },
                },
            )
            (root / "target.txt").write_text("x", encoding="utf-8")
            streams: dict[str, bytes] = {}

            def writer(stream: str, payload: bytes) -> None:
                streams[stream] = payload

            workspace_config = json.loads(config.read_text(encoding="utf-8"))
            from flowctl.agent_process_execution import prepare_agent_run

            executor, repo, workdir_path, targets, prompt = prepare_agent_run(
                executor_id=executor_id,
                repo_raw="workspace-root",
                workdir_raw=str(root),
                prompt_raw=user_prompt,
                target_raws=["target.txt"],
                workspace_root=root,
                workspace_config_file=config,
                workspace_config=workspace_config,
                root_repo="softos-agentic",
            )
            rc, _metadata = run_agent_process(
                executor=executor,
                repo=repo,
                workspace_root=root,
                workdir=workdir_path,
                targets=targets,
                prompt=prompt,
                shutil_which=lambda _: str(fake),
                subprocess_run=subprocess.run,
                stream_writer=writer,
            )
            return rc, streams

    def test_codex_fake_cli_integration(self) -> None:
        rc, streams = self._run_harness(
            harness_name="codex",
            adapter="codex",
            executable_name="codex",
            executor_id="codex",
        )
        self.assertEqual(0, rc)
        self.assertEqual(b"FAKE_STDOUT", streams.get("stdout"))
        self.assertEqual(b"FAKE_STDERR", streams.get("stderr"))

    def test_cursor_fake_cli_integration(self) -> None:
        rc, streams = self._run_harness(
            harness_name="cursor",
            adapter="cursor",
            executable_name="agent",
            executor_id="cursor",
        )
        self.assertEqual(0, rc)
        self.assertEqual(b"FAKE_STDOUT", streams.get("stdout"))
        self.assertEqual(b"FAKE_STDERR", streams.get("stderr"))

    def test_opencode_local_fake_cli_integration(self) -> None:
        rc, streams = self._run_harness(
            harness_name="opencode",
            adapter="opencode",
            executable_name="opencode",
            executor_id="opencode-local",
        )
        self.assertEqual(0, rc)
        self.assertEqual(b"FAKE_STDOUT", streams.get("stdout"))
        self.assertEqual(b"FAKE_STDERR", streams.get("stderr"))

    def test_option_shaped_contract_prompt_passes_fake_cli(self) -> None:
        for harness_name, adapter, executable_name, executor_id in (
            ("codex", "codex", "codex", "codex"),
            ("cursor", "cursor", "agent", "cursor"),
            ("opencode", "opencode", "opencode", "opencode-local"),
        ):
            with self.subTest(executor_id=executor_id):
                rc, streams = self._run_harness(
                    harness_name=harness_name,
                    adapter=adapter,
                    executable_name=executable_name,
                    executor_id=executor_id,
                    user_prompt="finish the slice",
                )
                self.assertEqual(0, rc)
                self.assertEqual(b"FAKE_STDOUT", streams.get("stdout"))
                self.assertEqual(b"FAKE_STDERR", streams.get("stderr"))

    def test_non_zero_exit_code_is_propagated_for_each_harness(self) -> None:
        cases = [
            ("codex", "codex", "codex", "codex"),
            ("cursor", "cursor", "agent", "cursor"),
            ("opencode", "opencode", "opencode", "opencode-local"),
        ]
        for harness_name, adapter, executable_name, executor_id in cases:
            with self.subTest(executor_id=executor_id):
                rc, _streams = self._run_harness(
                    harness_name=harness_name,
                    adapter=adapter,
                    executable_name=executable_name,
                    executor_id=executor_id,
                    exit_code=37,
                )
                self.assertEqual(37, rc)

    def test_unsafe_static_argv_rejected_before_fake_cli_launch(self) -> None:
        secret_argv = "SUPER_SECRET_ARGV_TOKEN"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = root / "codex"
            _write_harness_fake_cli(
                fake,
                harness={
                    "name": "codex",
                    "adapter": "codex",
                    "executable": str(fake),
                    "executor_id": "codex",
                    "static_argv": [secret_argv],
                    "expected_cwd": str(root.resolve()),
                    "workspace_root": str(root.resolve()),
                    "workdir": str(root.resolve()),
                    "targets": ["target.txt"],
                    "user_prompt": "ship it",
                    "expected_prompt": "unused",
                    "exit_code": 0,
                },
            )
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
            workspace_config = json.loads(config.read_text(encoding="utf-8"))
            from flowctl.agent_process_execution import AgentRunError, prepare_agent_run

            executor, repo, workdir, targets, prompt = prepare_agent_run(
                executor_id="codex",
                repo_raw="workspace-root",
                workdir_raw=str(root),
                prompt_raw="ship it",
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
                    shutil_which=lambda _: str(fake),
                    subprocess_run=subprocess.run,
                )
            diagnostic = str(ctx.exception)
            self.assertIn("argv estatico no permitido", diagnostic)
            self.assertNotIn(secret_argv, diagnostic)

    def test_command_agent_run_rejects_unsafe_static_argv_without_echoing_secrets(self) -> None:
        secret_prompt = "SUPER_SECRET_PROMPT_TOKEN"
        secret_env = "SUPER_SECRET_ENV_TOKEN"
        secret_argv = "SUPER_SECRET_ARGV_TOKEN"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = root / "codex"
            harness = {
                "name": "codex",
                "adapter": "codex",
                "executable": str(fake),
                "executor_id": "codex",
                "static_argv": ["--help"],
                "expected_cwd": str(root.resolve()),
                "workspace_root": str(root.resolve()),
                "workdir": str(root.resolve()),
                "targets": ["target.txt"],
                "user_prompt": secret_prompt,
                "expected_prompt": "unused",
                "exit_code": 0,
            }
            harness["expected_prompt"] = _expected_delivered_prompt(harness=harness)
            _write_harness_fake_cli(fake, harness=harness)
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
            with unittest.mock.patch.dict(os.environ, {"TEST_AGENT_SECRET": secret_env}, clear=False):
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
                        shutil_which=lambda _: str(fake),
                        subprocess_run=subprocess.run,
                    )
            diagnostic = str(ctx.exception)
            self.assertIn("argv estatico no permitido", diagnostic)
            self.assertNotIn(secret_prompt, diagnostic)
            self.assertNotIn(secret_env, diagnostic)
            self.assertNotIn(secret_argv, diagnostic)


def argparse_namespace(**kwargs: object) -> object:
    class Namespace:
        pass

    ns = Namespace()
    for key, value in kwargs.items():
        setattr(ns, key, value)
    return ns


if __name__ == "__main__":
    unittest.main()
