# ACP Executor Runtime V1

SoftOS keeps orchestration, Patch Units/DAG state, resource routing, provider/model policy, ownership, permissions policy, verification, review, and evidence in the control plane. ACP is only the transport used to talk to an executor.

## Transport selection

Executor entries in `workspace.config.json` accept additive fields:

```json
{
  "transport": "auto",
  "allow_cli_fallback": true,
  "permission_policy": "reject",
  "acp": {"executable": "agent", "argv": ["acp"], "auth_method": "cursor_login"}
}
```

`cli`, `acp`, and `auto` are supported. Entries that omit `transport` retain the legacy CLI path. `auto` probes the configured ACP executable, performs ACP session initialization, and falls back only before prompt submission when `allow_cli_fallback` is true. The fallback phase/reason is printed as `SOFTOS ACP fallback` and included in the structured execution evidence line.

Use `flow agent run ... --transport cli` or `--transport acp` to compare transports for the same executor and task.

## Runtime boundary

`prepare_agent_run()` resolves the executor, logical resource, worktree, targets, prompt contract, and resource-owned model/environment overlay. `ACPTransport` then performs only `initialize`, optional `authenticate`, `session/new`, `session/prompt`, streamed `session/update`, permission responses, `session/cancel`, and process shutdown. ACP traffic and prompts are not persisted.

ACP permission policy is SoftOS-owned and conservative: `reject` is the default; `allow_once` is explicit. CLI behavior remains unchanged, including its existing adapter flags.

## Discovered entrypoints

- Cursor Agent `agent acp` is installed and exposes native ACP over newline-delimited JSON-RPC stdio.
- OpenCode `opencode acp` is installed and exposes native ACP over stdio; the configured `opencode-softos acp` wrapper preserves the existing local worker/resource semantics.
- The installed Codex CLI exposes `app-server`, not native ACP. The workspace therefore names the separately installable `codex-acp` compatibility adapter explicitly; when it is absent, `auto` reports `acp_executable_unavailable` and uses CLI because fallback is enabled.

## Evidence

`flow agent run` emits a metadata-only `SOFTOS_EXECUTION_EVIDENCE` record on stderr containing executor/resource, requested/used transport, ACP session id (when available), timestamps, normalized result/cancellation, permission outcomes, fallback reason, and failure class. Prompts, streams, environment values, credentials, and rendered argv are excluded.
