# SoftOS Harness Core and Profiles

Spanish mirror: [docs/es/harness-core-and-profiles.es.md](./es/harness-core-and-profiles.es.md)

Source: `docs/harness-core-and-profiles.md`  
Last updated: 2026-05-07

This package separates reusable Harness Core policy from project-specific
profiles.

## What is new

- Reusable policy pack at `policies/harness-core/*`.
- Project profile contract at `profiles/<profile-id>/profile.json`.
- Open-source-safe profile example at `profiles/example-api-ticket/profile.json`.
- Stdlib-only validator at `scripts/harness/validate_profile.py`.
- Feature source spec at
  `specs/features/softos-harness-core-and-profiles.spec.md`.
- Usage and Cost Harness policy at `policies/harness-core/usage-and-cost.md`.

## Why

Harness practices often mix universal delivery controls with local conventions
such as repository labels, deploy commands, E2E runners, ticket systems, and
communication tools. This split keeps reusable policy open-source-safe while
allowing each project to bind the core to its own workflow.

## Core vs profile

| Layer | Owns | Example |
| --- | --- | --- |
| Core | lifecycle, gates, reviewer contracts, evidence, progress, PR readiness concepts, usage/cost telemetry | R1-R5, empty open questions, dry-run first, usage checkpoints |
| Profile | local tools, repo conventions, labels, deploy/E2E commands, mirror format, communication surfaces | repository labels, staging command, E2E runner |

## Included profiles

- `profiles/example-api-ticket/profile.json` - open-source-safe example profile.

Projects should create private profiles for organization-specific repositories,
labels, ticket systems, deploy commands, communication channels, and validation
runners.

## Validation

```bash
python3 scripts/harness/validate_profile.py --root . --json
```

The validator ensures:

- required core files exist
- core does not leak obvious project-private terms
- profiles extend `policies/harness-core`
- R1-R5 gates are declared
- label discovery, communication ledger, usage telemetry, and dry-run-first automation are present

## Adoption path

1. Copy or vendor the core policies.
2. Start with `profiles/example-api-ticket/profile.json` as a template.
3. Keep private profile data outside public source control when needed.
4. Run the validator in CI or before publishing profile changes.
