---
schema_version: 3
name: "ACP Executor Runtime V1"
description: "Add ACP as an optional preferred transport for supported SoftOS executors while retaining explicit CLI fallback."
status: draft
owner: platform
single_slice_reason: ""
multi_domain: false
phases: []
depends_on:
  - specs/000-foundation/spec-as-source-operating-model.spec.md
  - specs/000-foundation/repo-routing-and-worktree-orchestration.spec.md
  - specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - specs/features/agent-executors.spec.md
  - specs/features/coding-execution-runtime-v1.spec.md
required_runtimes:
  - python
required_services: []
required_capabilities: []
stack_projects: []
stack_services: []
stack_capabilities: []
targets:
  - ../../workspace.config.json
  - ../../flowctl/agent_executors.py
  - ../../flowctl/agent_executor_adapters.py
  - ../../flowctl/agent_process_execution.py
  - ../../flowctl/acp_transport.py
  - ../../flowctl/parser.py
  - ../../flowctl/tests/test_acp_transport.py
  - ../../flowctl/tests/test_agent_process_execution.py
  - ../../docs/**
  - ../../specs/features/acp-executor-runtime-v1.spec.md
---

# ACP Executor Runtime V1

## Objective

Make ACP the preferred execution transport for configured Cursor, Codex-compatible ACP, and OpenCode executors without changing SoftOS orchestration, Patch Units, resource selection, provider/model policy, permissions ownership, verification, review, or evidence contracts.

## Context and boundary

The existing path is `prepare_agent_run()` → adapter invocation → `execute_subprocess()`. This feature extends that boundary with `AgentTransport`; `CLITransport` preserves the current argv/subprocess behavior and `ACPTransport` owns only stdio JSON-RPC session mechanics. `Executor`, logical `Resource`, `Provider`, `Model`, `Transport`, and ACP `Session` remain distinct concepts.

## Scope

- Add additive executor configuration: `transport` (`cli`, `acp`, `auto`), `allow_cli_fallback` (boolean), ACP executable/argv override, and explicit ACP permission policy (`reject` or `allow_once`). Existing entries without these fields mean `cli` with fallback disabled.
- Implement ACP initialize, optional authentication, `session/new`, `session/prompt`, streamed `session/update`, final result, permission request response, cancellation, and clean process shutdown over newline-delimited JSON-RPC stdio.
- Normalize ACP outcomes into the existing execution result shape and metadata, including executor/resource, requested/used transport, session id, timing, result/cancellation, permission decisions, fallback reason, and failure class.
- `auto` probes ACP executable/protocol readiness before prompt submission and falls back to CLI only for pre-submission ACP availability/initialization failures when explicitly allowed; every fallback is visible in metadata/stderr.
- Keep OpenCode Local/Free/Go resource/provider/model resolution and process overlays independent from transport. ACP receives resolved resource context but never chooses a provider/model.
- Cover deterministic fake ACP agents and preserve all legacy CLI tests.

## Out of scope

No Gateway, Patch Unit, Supervisor, scheduler, database, daemon, TUI, model/provider credential routing, blind retries, CLI removal, PLG repository changes, or automatic dangerous permission approval.

## Invariants and failure semantics

- ACP is not an orchestrator; it cannot mutate DAG/state/evidence beyond the normalized result returned to SoftOS.
- Permission policy is SoftOS-owned. Default/reject and allow-once are explicit and testable; no silent auto-approval.
- ACP process/initialize/protocol failures map to `runtime_failure`; unsuccessful agent completion maps to `task_failure`; cancellation is explicit and never reported as success.
- Resource and model/provider selection occurs before transport selection and is identical for CLI and ACP.

## Acceptance criteria

- Tests prove ACP selection/availability, allowed and disabled fallback, initialization failure, streamed normalization, permission handling, cancellation, failure mapping, CLI parity, and resource/model/provider independence.
- `workspace.config.json` validates with ACP-capable entries for Cursor (`agent acp`), OpenCode (`opencode acp`), and a configurable Codex ACP adapter command; missing Codex adapter is reported as unavailable rather than guessed.
- Legacy configs without transport continue on CLI with unchanged argv, stream, exit-code, containment, and resource behavior.
- No credentials, raw prompts, or raw ACP traffic are persisted; structured execution metadata is sufficient to distinguish requested/used transport and fallback.

## Verification Matrix

```yaml
- name: acp-runtime-tests
  level: integration
  command: scripts/workspace_exec.sh python3 -m unittest discover -s flowctl/tests -p 'test_acp_transport.py'
  blocking_on: [ci]
  environments: [local]
- name: legacy-agent-tests
  level: integration
  command: scripts/workspace_exec.sh python3 -m unittest discover -s flowctl/tests -p 'test_agent_*.py'
  blocking_on: [ci]
  environments: [local]
- name: diff-check
  level: custom
  command: git diff --check
  blocking_on: [ci]
  environments: [local]
```
