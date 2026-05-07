# Readiness gated schema hardening

English source: [docs/readiness-gated-schema-hardening.md](../readiness-gated-schema-hardening.md)

Source: `docs/readiness-gated-schema-hardening.md`  
Last updated: 2026-05-06

Nota: Este espejo en espanol fue creado para cerrar el backlog de i18n. Se recomienda refinar la traduccion en una iteracion posterior.

# Readiness-Gated Schema Hardening

Spanish mirror: [docs/es/readiness-gated-schema-hardening.es.md](./es/readiness-gated-schema-hardening.es.md)

Source: `docs/readiness-gated-schema-hardening.md`  
Last updated: 2026-05-06

This note captures the reusable SoftOS pattern for schema hardening that depends on real data quality.

## Use this when

- `NOT NULL` depends on backfill
- a new FK may fail on dirty historical data
- uniqueness or constraint tightening must wait for remediation

## Standard sequence

1. Materialize nullable schema.
2. Add backfill/remediation tooling.
3. Add readiness reporting and stop conditions.
4. Keep hardening migration out of the default migration path.
5. Activate hardening only after readiness verification succeeds in the target environment.

## Preferred repo pattern

- Active path:
  - `database/migrations/`
- Candidate path:
  - `database/migrations/candidates/<wave>/`

The candidate migration is not part of normal `artisan migrate` until the readiness gate is satisfied.

## Required executable guardrail

The repo should expose a command or equivalent runnable path that:

- evaluates readiness from actual data
- emits machine-readable gate output
- exits `0` only when hardening is safe
- exits non-zero otherwise

Typical gate keys:

- `backfill_verified`
- `not_null_readiness`
- `schema_hardened`
- `stop_conditions_active`
- `evidence_complete_for_gate`

## Decision model

Only two outputs are valid:

- `prepared but not enabled`
- `enabled for rollout`

If stop conditions are active, the migration stays a candidate.

## Why this exists

It prevents the common failure mode where:

- CI proves a clean database can survive `NOT NULL`
- the migration is committed as active
- a dirtier environment later runs `artisan migrate` and fails

The rule is simple:

**readiness must be executable, and hardening must not auto-run before readiness is proven for the target environment.**
