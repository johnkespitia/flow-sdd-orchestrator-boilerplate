---
id: softos-harness-core-and-profiles
status: draft
owner: softos-harness
---

# SoftOS Harness Core and Profiles

## Summary

Separate reusable Harness Core policies from project-specific profiles so the
pattern can be adopted across projects without hardcoding private conventions.

## Problem

Delivery harnesses often combine generic gates with local details such as label
names, deploy flows, E2E commands, ticket systems, and communication surfaces.
That makes reuse difficult and risks leaking private project context.

## Goals

- Define project-neutral core policies.
- Define a profile contract for project-specific conventions.
- Provide a generic open-source-safe example profile.
- Provide a stdlib-only validator for core/profile structure.
- Keep external writes dry-run-first unless a profile explicitly enables them.

## Non-Goals

- Do not include private repository names, ticket links, channel links,
  credentials, or organization-specific deploy commands in the core package.
- Do not require every project to use the same ticket system, PR labels, E2E
  runner, or communication tool.

## Slices

1. `harness-core-policy-pack`
2. `harness-profile-contract`
3. `example-api-ticket-profile`
4. `harness-profile-validator`
5. `opensource-adoption-docs`

## Validation Plan

- Run `python3 scripts/harness/validate_profile.py --root . --json`.
- Confirm core policies have no obvious project-private terms.
- Confirm the example profile loads and declares required gates.
- Confirm profile automation is dry-run-first.

## Open Questions

None
