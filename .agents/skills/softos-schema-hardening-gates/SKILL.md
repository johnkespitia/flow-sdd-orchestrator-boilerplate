---
name: softos-schema-hardening-gates
description: Use when a schema change must be gated by real data readiness before hardening constraints such as NOT NULL, foreign keys, or destructive reshapes. Covers candidate migrations, readiness verification, stop conditions, and rollout-safe activation.
---

# SoftOS Schema Hardening Gates

Use this skill when a repo already has:

- materialized columns or transitional schema in place
- backfill or remediation tooling
- a need to harden schema only after data readiness is proven

This skill is for the transition from:

1. transitional schema
2. backfill + evidence
3. readiness decision
4. hardening activation

Read first:

- `../softos-agent-playbook/SKILL.md`
- `../softos-reference-spec-hardening/SKILL.md`
- `../../../docs/readiness-gated-schema-hardening.md`

## Outcome

At the end:

- the hardening migration is not accidentally auto-applied before readiness
- the workspace has an executable readiness gate
- rollout sequencing is explicit and evidence-backed
- handoffs distinguish clearly between:
  - hardening prepared
  - hardening enabled
  - hardening blocked

## When to use

Use this skill when one or more of these are true:

- a spec introduces `NOT NULL`, new FK constraints, or irreversible schema hardening
- the change is only safe after data backfill or remediation
- CI can prove readiness in one environment, but other environments may still be dirty
- a migration exists but should not yet live in the default `migrate` path

## Core model

Treat schema hardening as four distinct stages:

1. materialization
2. backfill + evidence
3. readiness gate
4. hardening activation

Do not collapse stages 3 and 4 into the same narrative closeout unless the environment being validated is the actual rollout environment and the spec explicitly allows that.

## Required artifacts

The preferred operating model is:

- active repo code for stages 1-3
- candidate migration for stage 4, outside the normal migration path
- executable readiness verifier returning success/failure
- handoff/report with gate state

## Rules

### 1. Candidate-first rule

If hardening is data-sensitive, the final migration should live outside the normal migration path until readiness is proven for the target environment.

Preferred pattern:

- active migrations: transitional/materialization only
- candidate migrations: `database/migrations/candidates/<wave>/...`

### 2. Executable gate rule

Readiness must not live only in docs or chat.

Provide an executable verifier that:

- runs the relevant dry-run/backfill/readiness logic
- reads the resulting gate data
- exits `0` only if hardening is safe
- exits non-zero otherwise

### 3. Gate vocabulary

Use explicit gate outputs such as:

- `backfill_verified`
- `not_null_readiness`
- `schema_hardened`
- `stop_conditions_active`
- `evidence_complete_for_gate`

### 4. No narrative enablement

Do not mark hardening as “ready” merely because:

- a migration file exists
- CI is green
- one clean environment passed

Hardening is enabled only when the gate says so for the relevant environment.

### 5. Stop-condition discipline

If a stop condition is active, the correct outcome is:

- block hardening
- preserve the candidate migration
- report the blocking evidence

Do not reclassify a stop condition as “small residual debt”.

## Preferred workflow

1. Audit current stage.
2. Separate readiness from hardening if they were mixed.
3. Move hardening migration out of the default path if needed.
4. Add or refine readiness verification command.
5. Ensure reports expose machine-readable gate state.
6. Validate that CI and handoffs reflect the same decision model.
7. Only then prepare the implementation prompt for the next wave.

## Review questions

Ask these before closing:

1. Can `artisan migrate` or the repo default migration flow apply the hardening before readiness is proven?
2. Is there an executable verifier that returns pass/fail for readiness?
3. Does the handoff distinguish `prepared` from `enabled`?
4. Would a dirty production database attempt the hardening automatically?
5. Is the next implementation wave clearly either:
   - readiness only
   - or hardening activation only

## Minimum validation

Run:

```bash
python3 ./flow ci spec <spec-path>
python3 ./flow ci repo <repo>
```

And confirm at least one executable readiness path exists in repo code or CI code.

## Stop rule

The hardening flow is not correct if any of these remain true:

- the final migration is active but rollout is supposed to be conditional
- readiness exists only as prose, not as a command/test/report
- a clean CI environment is being used to claim all environments are ready
- handoff text says “do not run this yet” while the repo would still run it automatically
