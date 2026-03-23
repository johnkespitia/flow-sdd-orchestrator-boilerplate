---
name: bmad-agent-router
description: Use when the user describes what to build and expects the AI to route and execute the corresponding BMAD workflow/agents via `flow workflow` and `flow bmad`.
---

# BMAD Agent Router

Use this skill when the user gives a development goal and wants automatic BMAD orchestration.

## Outcome

- Feature intake created with correct runtime/service/capability context.
- Recommended BMAD next step resolved.
- Feature execution started with slices.
- Governance gates run (`spec review`, `spec approve`, `ci spec`).

## Required Inputs

- Business goal (what to build).
- Target repo (or `root`).
- Runtime/service/capability hints when available.

If any input is missing, infer from workspace config and current specs.

## Workflow

### 1) Runtime readiness for BMAD

Check BMAD availability:

```bash
python3 ./flow bmad -- status
```

If unavailable:

```bash
python3 ./flow init --build
python3 ./flow bmad -- install --tools none --yes
python3 ./flow bmad -- status
```

Do not proceed with orchestration until BMAD status is healthy.

### 2) Intake a feature

```bash
python3 ./flow workflow intake <slug> \
  --title "<Feature Title>" \
  --repo <root|repo_id> \
  --runtime <runtime> \
  [--service <service-runtime>] \
  [--capability <capability>] \
  [--depends-on <foundation-or-domain-spec>] \
  --json
```

Notes:

- For `specs/features/**`, include dependencies to relevant `specs/000-foundation/**` and `specs/domains/**`.
- If no domain applies, include explicit rationale in the spec body: `no aplica domain porque <razon>`.

### 3) Route to BMAD next step

```bash
python3 ./flow workflow next-step <slug> --json
```

Use this output as the routing decision for the BMAD agent/workflow.

### 4) Execute feature

```bash
python3 ./flow workflow execute-feature <slug> --start-slices --json
```

### 5) Enforce governance gates

```bash
python3 ./flow spec review <slug>
python3 ./flow spec approve <slug> --approver <id>
python3 ./flow ci spec <slug>
```

If `ci spec` fails, patch spec/tests and rerun until green.

### 6) Optional operational checks

If implementation requires runtime services:

```bash
python3 ./flow stack up
python3 ./flow stack ps
```

Treat "container up + app down" as not ready; run runtime-specific readiness checks before closing.

## Rules

- Prefer `flow workflow ...` as the primary BMAD entrypoint.
- Do not skip intake context; avoid direct coding before orchestration.
- Keep all behavior changes backed by canonical specs in `specs/**`.
- Do not close a task without passing spec governance.

## Output Contract

Always report:

- intake command and result
- next-step decision payload
- execute-feature result
- review/approve/ci status
- unresolved blockers (if any)
