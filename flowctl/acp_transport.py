"""Minimal ACP stdio transport for SoftOS executor runs.

This module deliberately owns protocol mechanics only.  It does not select
resources/models, mutate Patch Units, or persist protocol traffic.
"""
from __future__ import annotations

import json
import os
import select
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Optional, Protocol, Sequence


@dataclass(frozen=True)
class ACPPermissionRequest:
    """Normalized permission request exposed to the SoftOS policy boundary."""

    tool_call_id: str | None
    title: str | None
    options: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class ACPTransportResult:
    exit_code: int
    final_result: str = ""
    streamed_text: str = ""
    session_id: str | None = None
    cancelled: bool = False
    permission_requests: tuple[dict[str, object], ...] = ()
    failure_class: str | None = None
    failure_detail: str | None = None
    submitted: bool = False


class CLITransport:
    """Compatibility transport retaining the existing subprocess semantics."""

    def probe(self, *, shutil_which: Callable[[str], Optional[str]]) -> tuple[bool, str | None]:
        return True, None

    def cancel(self) -> bool:
        return False

    def run(
        self,
        *,
        invocation,
        cwd: Path,
        subprocess_run: Callable[..., object],
        env: Mapping[str, str] | None = None,
    ) -> ACPTransportResult:
        kwargs: dict[str, object] = {
            "args": list(invocation.argv), "cwd": str(cwd), "shell": False, "capture_output": True,
        }
        if invocation.stdin is not None:
            kwargs["input"] = invocation.stdin.encode("utf-8")
        if env is not None:
            kwargs["env"] = dict(env)
        try:
            completed = subprocess_run(**kwargs)
        except OSError as exc:
            raise ACPTransportError("No pude lanzar el proceso del executor.", phase="runtime") from exc
        return ACPTransportResult(
            exit_code=int(getattr(completed, "returncode", 1)),
            streamed_text=(getattr(completed, "stdout", b"") or b"").decode("utf-8", errors="replace")
            if isinstance(getattr(completed, "stdout", b""), bytes) else str(getattr(completed, "stdout", "") or ""),
        )


class ACPTransportError(RuntimeError):
    def __init__(self, message: str, *, phase: str, submitted: bool = False) -> None:
        self.phase = phase
        self.submitted = submitted
        super().__init__(message)


PermissionHandler = Callable[[ACPPermissionRequest], str]


class AgentTransport(Protocol):
    """Small transport boundary shared by ACP and the legacy CLI path."""

    def cancel(self) -> bool: ...

    def probe(self, *, shutil_which: Callable[[str], Optional[str]]) -> tuple[bool, str | None]: ...

    def run(self, **kwargs: object) -> object: ...


class ACPTransport:
    """ACP client over a child process' newline-delimited JSON-RPC stdio."""

    def __init__(
        self,
        *,
        executable: str,
        argv: Sequence[str] = (),
        auth_method: str | None = None,
        permission_policy: str = "reject",
        popen_factory: Callable[..., subprocess.Popen] = subprocess.Popen,
        initialize_timeout: float = 15.0,
        session_timeout: float = 3600.0,
    ) -> None:
        self.executable = executable
        self.argv = tuple(argv)
        self.auth_method = auth_method
        self.permission_policy = permission_policy
        self._popen_factory = popen_factory
        self.initialize_timeout = initialize_timeout
        self.session_timeout = session_timeout
        self._process: subprocess.Popen | None = None
        self._write_lock = threading.Lock()
        self._session_id: str | None = None
        self._next_id = 1

    def probe(self, *, shutil_which: Callable[[str], Optional[str]]) -> tuple[bool, str | None]:
        """Probe executable/command shape without submitting a task."""
        candidate = Path(self.executable)
        if candidate.is_absolute():
            if not (candidate.is_file() and os.access(candidate, os.X_OK)):
                return False, "acp_executable_unavailable"
        elif shutil_which(self.executable) is None:
            return False, "acp_executable_unavailable"
        return True, None

    def _send(self, payload: Mapping[str, object]) -> int | None:
        process = self._process
        if process is None or process.stdin is None:
            raise ACPTransportError("ACP process is not running", phase="runtime")
        with self._write_lock:
            process.stdin.write((json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8"))
            process.stdin.flush()
        return payload.get("id") if isinstance(payload.get("id"), int) else None

    def _request(self, method: str, params: Mapping[str, object]) -> int:
        request_id = self._next_id
        self._next_id += 1
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": dict(params)})
        return request_id

    @staticmethod
    def _error_message(message: Mapping[str, object]) -> str:
        error = message.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or "ACP request failed")
        return "ACP request failed"

    @staticmethod
    def _extract_text(value: object) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return "".join(ACPTransport._extract_text(item) for item in value)
        if isinstance(value, dict):
            if isinstance(value.get("text"), str):
                return value["text"]
            return "".join(ACPTransport._extract_text(item) for item in value.values())
        return ""

    @staticmethod
    def _permission_decision(request: ACPPermissionRequest, policy: str) -> str:
        if policy == "allow_once":
            for option in request.options:
                option_id = str(option.get("optionId") or option.get("id") or "")
                kind = str(option.get("kind") or "").lower()
                if "allow" in option_id.lower() or "allow" in kind:
                    return option_id
        for option in request.options:
            option_id = str(option.get("optionId") or option.get("id") or "")
            if "reject" in option_id.lower() or "deny" in option_id.lower():
                return option_id
        return "reject-once"

    def _respond_permission(
        self,
        message: Mapping[str, object],
        *,
        permission_handler: PermissionHandler | None,
        records: list[dict[str, object]],
    ) -> None:
        params = message.get("params")
        params = params if isinstance(params, dict) else {}
        raw_options = params.get("options")
        options = tuple(item for item in raw_options if isinstance(item, dict)) if isinstance(raw_options, list) else ()
        request = ACPPermissionRequest(
            tool_call_id=str(params.get("toolCallId")) if params.get("toolCallId") is not None else None,
            title=str(params.get("title")) if params.get("title") is not None else None,
            options=options,
        )
        decision = permission_handler(request) if permission_handler is not None else self._permission_decision(request, self.permission_policy)
        if decision not in {"allow-once", "reject-once"}:
            decision = "reject-once"
        records.append({"tool_call_id": request.tool_call_id, "decision": decision, "title": request.title})
        self._send({
            "jsonrpc": "2.0",
            "id": message.get("id"),
            "result": {"outcome": {"outcome": "selected", "optionId": decision}},
        })

    def cancel(self) -> bool:
        if self._process is None or self._session_id is None:
            return False
        try:
            self._send({
                "jsonrpc": "2.0",
                "method": "session/cancel",
                "params": {"sessionId": self._session_id},
            })
            return True
        except (BrokenPipeError, ACPTransportError, OSError):
            return False

    def run(
        self,
        *,
        cwd: Path,
        prompt: str,
        env: Mapping[str, str] | None = None,
        permission_handler: PermissionHandler | None = None,
        cancel_event: threading.Event | None = None,
        stream_writer: Callable[[str, bytes], None] | None = None,
    ) -> ACPTransportResult:
        command = [self.executable, *self.argv]
        stderr_chunks: list[bytes] = []
        updates: list[str] = []
        permissions: list[dict[str, object]] = []
        process: subprocess.Popen | None = None
        submitted = False
        cancelled = False
        final_result = ""
        session_id: str | None = None

        def drain_stderr() -> None:
            if process is None or process.stderr is None:
                return
            for chunk in iter(process.stderr.readline, b""):
                if chunk:
                    stderr_chunks.append(chunk)

        try:
            try:
                process = self._popen_factory(
                    command,
                    cwd=str(cwd),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=False,
                    bufsize=0,
                    env=dict(env) if env is not None else None,
                )
            except OSError as exc:
                raise ACPTransportError("No pude lanzar el proceso ACP.", phase="runtime") from exc
            self._process = process
            stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
            stderr_thread.start()
            init_id = self._request("initialize", {
                "protocolVersion": 1,
                "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}, "terminal": False},
                "clientInfo": {"name": "softos", "version": "acp-v1"},
            })
            pending = {init_id: "initialize"}
            auth_id: int | None = None
            session_new_id: int | None = None
            prompt_id: int | None = None
            deadline = __import__("time").monotonic() + self.initialize_timeout
            while True:
                if cancel_event is not None and cancel_event.is_set() and session_id is not None and not cancelled:
                    cancelled = self.cancel()
                    if cancelled:
                        break
                if process.stdout is None:
                    raise ACPTransportError("ACP stdout unavailable.", phase="runtime", submitted=submitted)
                ready, _, _ = select.select([process.stdout.fileno()], [], [], 0.1)
                if not ready:
                    if process.poll() is not None:
                        raise ACPTransportError("ACP process exited before completing the session.", phase="runtime", submitted=submitted)
                    if __import__("time").monotonic() > deadline:
                        raise ACPTransportError("ACP session timeout.", phase="runtime", submitted=submitted)
                    continue
                raw = process.stdout.readline()
                if not raw:
                    raise ACPTransportError("ACP stream closed unexpectedly.", phase="protocol", submitted=submitted)
                try:
                    message = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ACPTransportError("ACP emitted invalid JSON.", phase="protocol", submitted=submitted) from exc
                if not isinstance(message, dict):
                    continue
                if message.get("method") == "session/request_permission":
                    self._respond_permission(message, permission_handler=permission_handler, records=permissions)
                    continue
                if message.get("method") == "session/update":
                    params = message.get("params") if isinstance(message.get("params"), dict) else {}
                    update = params.get("update") if isinstance(params.get("update"), dict) else params
                    content = update.get("content") if isinstance(update, dict) else None
                    text = self._extract_text(content)
                    if update.get("sessionUpdate") == "agent_message_chunk" and text:
                        updates.append(text)
                        if stream_writer is not None:
                            stream_writer("stdout", text.encode("utf-8"))
                    continue
                message_id = message.get("id")
                if message_id not in pending:
                    continue
                operation = pending.pop(message_id)
                if "error" in message:
                    raise ACPTransportError(self._error_message(message), phase=operation, submitted=submitted)
                result = message.get("result")
                if operation == "initialize":
                    if self.auth_method:
                        auth_id = self._request("authenticate", {"methodId": self.auth_method})
                        pending[auth_id] = "authenticate"
                    else:
                        session_new_id = self._request("session/new", {"cwd": str(cwd), "mcpServers": []})
                        pending[session_new_id] = "session"
                elif operation == "authenticate":
                    session_new_id = self._request("session/new", {"cwd": str(cwd), "mcpServers": []})
                    pending[session_new_id] = "session"
                elif operation == "session":
                    if not isinstance(result, dict) or not result.get("sessionId"):
                        raise ACPTransportError("ACP session/new returned no session id.", phase="session", submitted=False)
                    session_id = str(result["sessionId"])
                    self._session_id = session_id
                    deadline = __import__("time").monotonic() + self.session_timeout
                    prompt_id = self._request("session/prompt", {"sessionId": session_id, "prompt": [{"type": "text", "text": prompt}]})
                    pending[prompt_id] = "prompt"
                    submitted = True
                elif operation == "prompt":
                    stop_reason = ""
                    if isinstance(result, dict):
                        stop_reason = str(result.get("stopReason") or "").lower()
                        final_result = str(result.get("result") or result.get("text") or result.get("stopReason") or "")
                    if stop_reason in {"cancelled", "canceled"}:
                        cancelled = True
                    break
            task_failed = final_result.lower() in {"error", "failed", "failure"}
            if stream_writer is not None and stderr_chunks:
                stream_writer("stderr", b"".join(stderr_chunks))
            return ACPTransportResult(
                exit_code=130 if cancelled else (1 if task_failed else 0),
                final_result=final_result,
                streamed_text="".join(updates),
                session_id=session_id,
                cancelled=cancelled,
                permission_requests=tuple(permissions),
                submitted=submitted,
                failure_class="task_failure" if task_failed else None,
            )
        finally:
            if process is not None:
                try:
                    if process.stdin is not None:
                        process.stdin.close()
                except OSError:
                    pass
                try:
                    process.wait(timeout=2)
                except (subprocess.TimeoutExpired, OSError):
                    try:
                        process.terminate()
                        process.wait(timeout=1)
                    except (subprocess.TimeoutExpired, OSError):
                        process.kill()
                for stream in (process.stdout, process.stderr):
                    try:
                        if stream is not None:
                            stream.close()
                    except OSError:
                        pass
            self._process = None
            self._session_id = None
