# OpenCode Execution Resources (SoftOS V1)

> Español: [OpenCode Execution Resources](es/opencode-execution-resources.es.md)

This document is the repository-owned product contract for SoftOS logical OpenCode
resources. It distinguishes portable repository configuration from machine-local
OpenCode state, and local worker/profile execution from direct cloud execution.

It does **not** encode concrete providers, concrete models, credentials, tokens,
auth payloads, or workstation-specific absolute paths as SoftOS product truth.

## 1. Ownership boundaries

| Surface | Owns | Must not own |
| --- | --- | --- |
| SoftOS Core / policy / adapters | Logical resource IDs, capabilities, availability, capacity, cost tier, selection priority, failure semantics, model-agnostic invocation | Provider/model identity branches, `--model` / `--provider` / `--resource` CLI flags, credentials |
| `workspace.config.json` executor + resource registry | Executor harness IDs, underlying executables, logical resource metadata (including local capacity `1`) | Tokens, permanent free/Go model names, local worker prompt/profile body |
| Repository `opencode.json` | Portable `softos-local-worker` profile (bounded local worker configuration) | Secrets, machine-specific absolute paths, concrete provider/model product contracts |
| Process execution harness | Resource selection before launch, logical resource ID propagation, validated process-local environment overlay merge | Wholesale environment replacement, credential serialization, adapter argv model flags |
| `~/.config/opencode/**`, wrappers, auth stores, env overrides | Machine-local materialization (auth, temporary model inventory, local endpoints, optional workstation wrappers) | Canonical SoftOS product policy |

`docs/opencode-local-executor.md` remains historical workstation diagnostic notes.
This document is the V1 resource contract.
See also `docs/execution-runtime-compatibility.md` for the validated supervisor sandbox baseline and runtime/platform capability boundary.

## 2. Logical resources

SoftOS represents three logical resources behind the existing `opencode` adapter
family. Executor IDs remain harness identities; logical resources reference an
underlying executor.

| Logical resource | Cost/tier | Capacity | Underlying executor | Model resolution |
| --- | --- | ---: | --- | --- |
| `opencode-local` | local | **1** | local wrapper executor (`opencode-softos`) | Owned by the repository-owned `softos-local-worker` profile; Core does not branch on model or provider identity |
| `opencode-free` | cloud/free | conservative | generic direct OpenCode (`opencode`) | Dynamically choose from currently available free candidates; no permanent free model name |
| `opencode-go` | cloud/paid-low | conservative | same generic direct OpenCode when auth evidence exists | Dynamic after OpenCode-managed authentication; starts `AUTH_UNCONFIGURED`; no permanent Go model name |

Core and generic adapters stay model/provider agnostic. SoftOS does not add
`--resource`, `--model`, or `--provider` CLI flags for V1. Legacy
`flow agent run <executor-id> ...` continues to work; a positional selector may
resolve as a logical resource ID first, then its underlying executor.

## 3. Local worker/profile execution (`opencode-local`)

Local execution path:

```text
SoftOS selects logical resource opencode-local
  -> underlying executor opencode-local (executable: opencode-softos)
  -> repository-owned softos-local-worker profile from opencode.json
  -> OpenCode process uses that worker/profile
  -> model/provider selection remains inside the worker/profile + machine-local OpenCode state
```

Contract:

- `opencode.json` is the **canonical portable source** for the `softos-local-worker`
  definition (bounded prompt, mode, step budget, permissions).
- The profile intentionally omits concrete `model` / `provider` product fields so
  SoftOS Core stays identity-agnostic. Any concrete local endpoint or model choice
  is machine-local OpenCode materialization, not a SoftOS registry contract.
- Logical capacity remains **1**. Prefer one fresh bounded worker session per
  suitable Patch Unit; do not assign a whole product slice monolithically to the
  local resource.
- SoftOS does not permanently encode the worker name in adapter argv. Local SoftOS
  launches use the local wrapper/executor path so the process selects
  `softos-local-worker` without generic model flags.
- Repository config does **not** set a project-wide `default_agent` that cloud
  Free/Go processes would inherit. Worker selection for SoftOS local runs is
  process-scoped to the local resource path.

## 4. Direct cloud execution (`opencode-free` / `opencode-go`)

Cloud execution path:

```text
SoftOS selects logical resource opencode-free or opencode-go
  -> underlying generic executor opencode (executable: opencode)
  -> dynamic model resolution for that cloud resource
  -> validated process-local OPENCODE_CONFIG_CONTENT overlay carries only the resolved model
  -> subprocess launch (no softos-local-worker / local wrapper inheritance)
```

Contract:

- Free and Go remain **generic/direct** OpenCode cloud resources. They must **not**
  execute through `opencode-softos` / `softos-local-worker`, and must **not**
  inherit local worker/profile model/provider/profile configuration unless the
  same model/provider was independently resolved for that cloud resource.
- Resolved Free/Go models must affect the **spawned OpenCode process**, not
  diagnostics alone. The harness applies a validated process-local environment
  overlay (typically `OPENCODE_CONFIG_CONTENT` with the resolved model object).
- The overlay is process-local only: never persisted to Git or evidence; contains
  no credentials; does not persist raw provider/auth payloads; merges onto a copy
  of the inherited environment rather than replacing it wholesale; and scrubs
  local OpenCode config carriers so Free/Go do not pick up local worker/profile
  selection.
- `opencode-go` remains non-launchable while availability is `AUTH_UNCONFIGURED`.
  Authentication stays external and machine-local; SoftOS does not invent token
  names, store secrets, or claim auth without supported OpenCode evidence.

## 5. Portable repository config vs machine-local state

Canonical (repository):

- `opencode.json` — portable `softos-local-worker` profile and existing project MCP
  activation.
- `workspace.config.json` — model-agnostic executors and logical resource metadata.

Machine-local (not canonical product truth):

- `~/.config/opencode/**`
- workstation wrappers such as `opencode-softos`
- authentication stores and temporary model inventories
- environment overrides and local endpoints

Do not treat `~/.config/opencode` as the portable SoftOS source of truth. Do not
commit credentials, tokens, auth payloads, or machine-specific absolute paths.

## 6. Explicit non-goals for this contract

- No durable scheduler, leases, run database, Gateway, LangGraph, secret store,
  merge, or release behavior changes are implied by this document.
- No concrete vendor model or provider identity (including temporary workstation
  experiments) is a SoftOS product contract.
- No SoftOS CLI expansion for `--resource`, `--model`, or `--provider`.
- Installing or authenticating OpenCode remains an operator concern outside Git.
