from __future__ import annotations

import json
import stat
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from flowctl.acp_transport import ACPTransport, ACPTransportError
from flowctl.agent_executors import AgentExecutor
from flowctl.agent_process_execution import _default_stream_writer, run_agent_process
from flowctl.agent_executor_adapters import GenericStdinAdapter
from unittest import mock


def _write_acp_agent(path: Path, *, permission: bool = False, init_failure: bool = False, wait_cancel: bool = False) -> None:
    script = r'''
import json, sys
for line in sys.stdin:
    msg = json.loads(line)
    method = msg.get("method")
    if method == "initialize":
        if INIT_FAILURE:
            print(json.dumps({"jsonrpc":"2.0","id":msg["id"],"error":{"message":"init failed"}}), flush=True)
        else:
            print(json.dumps({"jsonrpc":"2.0","id":msg["id"],"result":{"protocolVersion":1}}), flush=True)
    elif method == "session/new":
        print(json.dumps({"jsonrpc":"2.0","id":msg["id"],"result":{"sessionId":"s-fake"}}), flush=True)
    elif method == "session/prompt":
        print(json.dumps({"jsonrpc":"2.0","method":"session/update","params":{"update":{"sessionUpdate":"agent_message_chunk","content":{"type":"text","text":"hello"}}}}), flush=True)
        if WAIT_CANCEL:
            continue
        if PERMISSION:
            print(json.dumps({"jsonrpc":"2.0","id":77,"method":"session/request_permission","params":{"toolCallId":"t1","title":"run shell","options":[{"optionId":"allow-once"},{"optionId":"reject-once"}]}}), flush=True)
        print(json.dumps({"jsonrpc":"2.0","id":msg["id"],"result":{"stopReason":"end_turn"}}), flush=True)
    elif method == "session/cancel":
        print(json.dumps({"jsonrpc":"2.0","method":"session/update","params":{"update":{"sessionUpdate":"agent_message_chunk","content":{"type":"text","text":"cancelled"}}}}), flush=True)
'''
    source = "INIT_FAILURE = %r\nPERMISSION = %r\nWAIT_CANCEL = %r\n" % (init_failure, permission, wait_cancel) + script
    path.write_text("#!/usr/bin/env python3\n" + source, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class ACPTransportTests(unittest.TestCase):
    def test_default_writer_flushes_each_payload(self) -> None:
        class RecordingStream:
            def __init__(self) -> None:
                self.events: list[tuple[str, str]] = []

            def write(self, value: str) -> None:
                self.events.append(("write", value))

            def flush(self) -> None:
                self.events.append(("flush", ""))

        stream = RecordingStream()
        with mock.patch("flowctl.agent_process_execution.sys.stdout", stream):
            _default_stream_writer("stdout", b"chunk")
        self.assertEqual([("write", "chunk"), ("flush", "")], stream.events)

    def test_session_stream_and_permission_normalize(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            agent = Path(tmp) / "acp-agent"
            _write_acp_agent(agent, permission=True)
            chunks: list[bytes] = []
            result = ACPTransport(executable=str(agent), permission_policy="reject").run(
                cwd=Path(tmp), prompt="read README", stream_writer=lambda _s, b: chunks.append(b)
            )
            self.assertEqual(0, result.exit_code)
            self.assertEqual("s-fake", result.session_id)
            self.assertEqual("hello", result.streamed_text)
            self.assertEqual([b"hello"], chunks)
            self.assertEqual("reject-once", result.permission_requests[0]["decision"])

    def test_run_agent_process_uses_default_writer_for_acp_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            agent = Path(tmp) / "acp-agent"
            _write_acp_agent(agent)
            executor = AgentExecutor(
                "test",
                "test",
                str(agent),
                (),
                transport="acp",
                acp_executable=str(agent),
            )
            emitted: list[tuple[str, bytes]] = []
            with mock.patch("flowctl.agent_process_execution.resolve_adapter", return_value=GenericStdinAdapter("test")):
                with mock.patch(
                    "flowctl.agent_process_execution._default_stream_writer",
                    side_effect=lambda stream, payload: emitted.append((stream, payload)),
                ):
                    code, metadata = run_agent_process(
                        executor=executor,
                        repo="root",
                        workspace_root=Path(tmp),
                        workdir=Path(tmp),
                        targets=(".",),
                        prompt="x",
                        shutil_which=lambda _value: str(agent),
                        subprocess_run=subprocess.run,
                    )
            self.assertEqual(0, code)
            self.assertEqual("acp", metadata.transport_used)
            self.assertEqual([("stdout", b"hello"), ("stdout", b"\n")], emitted)

    def test_custom_acp_writer_preserves_exact_stream_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            agent = Path(tmp) / "acp-agent"
            _write_acp_agent(agent)
            executor = AgentExecutor(
                "test",
                "test",
                str(agent),
                (),
                transport="acp",
                acp_executable=str(agent),
            )
            emitted: list[tuple[str, bytes]] = []
            with mock.patch(
                "flowctl.agent_process_execution.resolve_adapter",
                return_value=GenericStdinAdapter("test"),
            ):
                code, metadata = run_agent_process(
                    executor=executor,
                    repo="root",
                    workspace_root=Path(tmp),
                    workdir=Path(tmp),
                    targets=(".",),
                    prompt="x",
                    shutil_which=lambda _value: str(agent),
                    subprocess_run=subprocess.run,
                    stream_writer=lambda stream, payload: emitted.append((stream, payload)),
                )
            self.assertEqual(0, code)
            self.assertEqual("acp", metadata.transport_used)
            self.assertEqual([("stdout", b"hello")], emitted)

    def test_explicit_allow_once_permission(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            agent = Path(tmp) / "acp-agent"
            _write_acp_agent(agent, permission=True)
            result = ACPTransport(executable=str(agent), permission_policy="allow_once").run(cwd=Path(tmp), prompt="x")
            self.assertEqual("allow-once", result.permission_requests[0]["decision"])

    def test_initialize_failure_is_protocol_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            agent = Path(tmp) / "acp-agent"
            _write_acp_agent(agent, init_failure=True)
            with self.assertRaises(ACPTransportError) as ctx:
                ACPTransport(executable=str(agent)).run(cwd=Path(tmp), prompt="x")
            self.assertEqual("initialize", ctx.exception.phase)
            self.assertFalse(ctx.exception.submitted)

    def test_cancellation_sends_session_cancel_and_normalizes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            agent = Path(tmp) / "acp-agent"
            _write_acp_agent(agent, wait_cancel=True)
            cancel_event = threading.Event()
            def trigger() -> None:
                import time
                time.sleep(0.05)
                cancel_event.set()
            threading.Thread(target=trigger, daemon=True).start()
            result = ACPTransport(executable=str(agent)).run(cwd=Path(tmp), prompt="x", cancel_event=cancel_event)
            self.assertTrue(result.cancelled)
            self.assertEqual(130, result.exit_code)

    def test_auto_falls_back_only_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            agent = Path(tmp) / "cli-agent"
            agent.write_text("#!/usr/bin/env python3\nimport sys; print('CLI_OK')\n", encoding="utf-8")
            agent.chmod(agent.stat().st_mode | stat.S_IXUSR)
            executor = AgentExecutor("test", "test", str(agent), (), transport="auto", allow_cli_fallback=True, acp_executable=str(Path(tmp) / "missing"))
            with mock.patch("flowctl.agent_process_execution.resolve_adapter", return_value=GenericStdinAdapter("test")):
                code, metadata = run_agent_process(executor=executor, repo="root", workspace_root=Path(tmp), workdir=Path(tmp), targets=(".",), prompt="x", shutil_which=lambda value: str(agent) if value == str(agent) else None, subprocess_run=subprocess.run)
            self.assertEqual(0, code)
            self.assertEqual("cli", metadata.transport_used)
            self.assertIn("acp_executable_unavailable", metadata.fallback_reason or "")

    def test_auto_without_fallback_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor = AgentExecutor("test", "test", "missing-cli", (), transport="auto", allow_cli_fallback=False, acp_executable="missing-acp")
            with mock.patch("flowctl.agent_process_execution.resolve_adapter", return_value=GenericStdinAdapter("test")):
                with self.assertRaisesRegex(Exception, "ACP adapter executable|unavailable"):
                    run_agent_process(executor=executor, repo="root", workspace_root=Path(tmp), workdir=Path(tmp), targets=(".",), prompt="x", shutil_which=lambda _value: None, subprocess_run=subprocess.run)

    def test_initialization_failure_can_fall_back_before_prompt_submission(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            acp = Path(tmp) / "acp-agent"
            cli = Path(tmp) / "cli-agent"
            _write_acp_agent(acp, init_failure=True)
            cli.write_text("#!/usr/bin/env python3\nprint('CLI_OK')\n", encoding="utf-8")
            cli.chmod(cli.stat().st_mode | stat.S_IXUSR)
            executor = AgentExecutor("test", "test", str(cli), (), transport="auto", allow_cli_fallback=True, acp_executable=str(acp))
            with mock.patch("flowctl.agent_process_execution.resolve_adapter", return_value=GenericStdinAdapter("test")):
                code, metadata = run_agent_process(executor=executor, repo="root", workspace_root=Path(tmp), workdir=Path(tmp), targets=(".",), prompt="x", shutil_which=lambda value: str(Path(value)) if value in {str(acp), str(cli)} else None, subprocess_run=subprocess.run)
            self.assertEqual(0, code)
            self.assertEqual("cli", metadata.transport_used)
            self.assertIn("initialize", metadata.fallback_reason or "")


if __name__ == "__main__":
    unittest.main()
