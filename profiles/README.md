# SoftOS Harness Profiles

Spanish mirror: [profiles/es/README.es.md](./es/README.es.md)

Profiles bind the generic Harness Core to a specific organization, repository
set, delivery workflow, and toolchain.

## What is new

- Profile contract materialized in `profiles/<profile-id>/profile.json`.
- Example profile added at `profiles/example-api-ticket/profile.json`.
- Validation available via `python3 scripts/harness/validate_profile.py --root . --json`.

A profile owns:

- ticket systems and work item key patterns
- repository mirror format
- labels and PR conventions
- staging/deploy/E2E strategy
- communication surfaces
- expected CI/check names
- reviewer/owner discovery rules
- redaction and privacy rules

Core policies must remain project-neutral. Profiles may include
project-specific conventions, but should avoid secrets and private links unless
the profile is kept private/local.

Usage/cost telemetry is enabled through `usage_telemetry` in each profile. The reporting contract requires progress-update checkpoints and closeout summaries, with every value labeled as `exact`, `provider_reconciled`, or `estimated`.
