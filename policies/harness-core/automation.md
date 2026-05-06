# Dry-Run-First Automation

Automation should make the workflow repeatable without removing human gates.

## Rule

Every automation starts with `--dry-run` and produces local evidence before it
mutates external systems.

## First automation capabilities

1. `bootstrap` — create initial artifacts.
2. `gate-check` — validate active gates and stale evidence.
3. `exact-revision-e2e` — validate the deployed revision for E2E.
4. `pr-readiness` — validate branch/commit/PR metadata.
5. `communication-ledger` — draft or publish state updates.

## Write safety

External writes require an explicit profile capability and user/tool
authorization. If writes are unavailable, automation should produce exact drafts
and target surfaces.
