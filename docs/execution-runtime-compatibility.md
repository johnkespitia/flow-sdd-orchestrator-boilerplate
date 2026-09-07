# Execution Runtime Compatibility and Supervisor Sandbox Boundary

> Spanish mirror: [Execution Runtime Compatibility and Supervisor Sandbox Boundary](es/execution-runtime-compatibility.es.md)

Source: `docs/execution-runtime-compatibility.md`
Last updated: 2026-09-07

This document records the currently validated SoftOS platform boundary between a supervisor and an execution runtime.
It complements `docs/opencode-execution-resources.md` and `specs/features/coding-execution-runtime-v1.spec.md`.

It documents observed behavior and the architectural contract. It does not implement the runtime boundary.

## Canonical locations

- Base workspace execution configuration: `workspace.config.json`
- Coding Execution Runtime V1 spec: `specs/features/coding-execution-runtime-v1.spec.md`
- Coding Execution Runtime resource contract: `docs/opencode-execution-resources.md`
- Runtime/platform compatibility baseline: this document

## Validated current behavior

Validated on Codex CLI 0.153.4 under WSL/Linux.

| Command or observation | Result | What it shows |
| --- | --- | --- |
| `codex doctor` | restricted fs + restricted network; approval `OnRequest`; managed proxy not configured | The supervisor is already sandboxed and must not assume host-like reachability |
| `codex exec -s workspace-write` | approval `never`; sandbox `workspace-write` | Explicit workspace-write execution is still inside a restricted boundary |
| `codex exec -a on-request` | rejected | `codex exec` does not accept that approval flag form |
| `codex exec -c 'approval_policy="on-request"'` | accepted by strict config parsing, but approval still `never` | Parsing acceptance does not imply the execution boundary changed |
| `codex exec --approve-for-me --sandbox workspace-write` | rejected as an invalid combination | Approval convenience flags do not override explicit sandbox selection |
| `getent hosts api2.cursor.sh` and `curl https://api2.cursor.sh` inside workspace-write | DNS/HTTPS blocked; `GETENT_EXIT=2`, `CURL_EXIT=6` | Network reachability is constrained by the supervisor sandbox |
| child executors launched by Codex | inherit the supervisor sandbox/network boundary | Executor availability is not the same as runtime compatibility |
| router-level shell policy | can reject dangerous shell patterns independently of Linux sandboxing | Command-policy rejection and sandbox rejection are distinct controls |

These observations are version- and environment-specific evidence. They are the current validation baseline, not a guarantee about future hosts or future CLI versions.

## Architectural contract

SoftOS treats executor availability and runtime compatibility as separate concerns.

- Executor availability answers whether a configured CLI exists and can be invoked.
- Runtime compatibility answers whether the selected execution runtime can satisfy the required host capabilities.
- A supervisor must not assume unrestricted network access, Docker daemon access, GPU access, privileged host capabilities, or arbitrary external executor connectivity.
- Those capabilities belong to the execution runtime boundary, not to SoftOS Core policy.

Capability vocabulary:

| Capability | Meaning |
| --- | --- |
| `network_required` | The work needs network access mediated by the runtime, not an implicit assumption of host reachability |
| `docker_required` | The work needs Docker or equivalent container runtime mediation |
| `gpu_required` | The work needs GPU access or GPU-backed runtime mediation |
| `local_service_required` | The work needs a local service or local endpoint provided by runtime or machine policy |

SoftOS records capability requirements as abstract labels. Actual destinations, endpoints, allowlists, proxies, and host-specific network rules belong to runtime or machine policy, not to repository product policy.
Do not hardcode provider domains, provider endpoints, or vendor-specific hostnames into SoftOS Core documentation.

## Future capability, not yet implemented

The following are future runtime capabilities, not current SoftOS behavior:

- managed network mediation
- per-runtime allowlists
- proxy-based routing for specific executor classes
- Docker bridge mediation exposed to the supervisor as a generic solution
- provider-specific destination lists embedded in repository policy

If these are added later, they must be described as runtime capabilities and validated against the current workspace policy. They must not be presented as already configured.
