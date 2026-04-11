---
name: softos-agent-memory-playbook
description: Use when a SoftOS task can benefit from reusable agent memory, especially spec hardening, release troubleshooting, gateway work, schema hardening, staging preflight, or multi-agent handoffs. This skill defines how to use Engram-style memory safely as consultive context, never as source of truth.
---

# SoftOS Agent Memory Playbook

Use this skill when a task can benefit from past SoftOS learnings across sessions or agents.

## Outcomes

- Agents recover relevant project learnings before repeating discovery.
- Handoffs preserve reusable lessons, not just chat summaries.
- Memory remains consultive and never overrides specs, plans, reports, CI, or release evidence.
- Secrets and sensitive data are never persisted.

## Source of truth boundary

Authoritative:

- `specs/**`
- `AGENTS.md`
- `workspace.config.json`
- `.flow/reports/**`
- release manifests/promotions
- CI and verification outputs

Consultive:

- Engram memories
- agent session summaries
- recalled gotchas
- previous outcomes

If memory conflicts with an authoritative artifact, trust the artifact and optionally save a corrected memory after verification.

## Default workflow

0. Check availability when the task can benefit from memory:

```bash
python3 ./flow memory doctor --json
```

Engram is installed automatically inside the SoftOS devcontainer. Project memory is isolated by
`ENGRAM_DATA_DIR=/workspace/.flow/memory/engram`; do not use a host-global Engram database for
SoftOS workspaces unless the user explicitly asks for cross-project memory.

1. At task start, search memory by project plus task surface:

```bash
python3 ./flow memory smoke --json
python3 ./flow memory search "softos <spec-or-area>" --json
```

2. Use recalled memory only to guide discovery. Still read the relevant specs and files.

3. Before implementation, save no memory unless a reusable decision is already confirmed by source artifacts.

4. At closeout, save reusable outcomes:

```bash
python3 ./flow memory save "SoftOS outcome: <area>" --body "TYPE: outcome
Project: softos-sdd-orchestrator
Area: <spec-or-hot-area>
What: <what changed or was validated>
Why: <why it matters>
Where: <files/specs/reports>
Evidence: <commands run>
Learned: <reusable lesson>"
```

5. If Engram is unavailable, continue without blocking the SDLC.

For an installation/write smoke after a devcontainer rebuild:

```bash
python3 ./flow memory smoke --save --json
```

## What to save

- recurring gotchas, such as spec governance formatting requirements
- release failure causes and resolutions
- repo/runtime-specific setup details
- verified hardening patterns
- multi-agent handoff lessons
- smoke commands that proved a boundary

## What not to save

- secrets, tokens, credentials, private keys
- raw customer data or PII
- speculative conclusions not verified by code/spec/tests
- full copyrighted documents
- noisy command logs without a reusable lesson
- temporary local paths unless they identify a stable workspace artifact

## Usage by SoftOS activity

### Spec hardening

- recall by spec slug, foundation, domain, and hot_area
- compare recalled patterns against the current spec
- harden only what the current spec and foundations justify

### Gateway and autonomy work

- recall previous boundaries and stop conditions
- verify against current specs before changing behavior
- save new outcomes only after unit/spec CI passes

### Release work

- recall prior release blockers, auth issues, tag/changelog gotchas, and staging preflight outcomes
- do not publish based on memory; run release commands and evidence gates

### Multi-agent handoff

- save only durable handoff facts:
  - what was completed
  - what was validated
  - what remains blocked
  - exact evidence commands

## Minimum memory shape

Prefer this structure:

```text
TYPE: gotcha|decision|outcome|handoff
Project: softos-sdd-orchestrator
Area: <spec slug, repo, runtime, or hot_area>
What: <concise fact>
Why: <impact>
Where: <source files or reports>
Evidence: <commands or commit/tag>
Learned: <reusable instruction>
```

## Safety rules

- Memory is optional. Missing Engram must not fail `flow` commands.
- Do not add Engram as a required runtime for unrelated specs.
- Do not store memories automatically from arbitrary command output.
- Prefer explicit agent saves after verification.
- If a memory is stale, save a corrective memory with evidence rather than silently relying on the old one.
