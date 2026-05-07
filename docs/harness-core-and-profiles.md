# SoftOS Harness Core and Profiles

This package separates reusable Harness Core policy from project-specific
profiles.

## Why

Harness practices often mix universal delivery controls with local conventions
such as repository labels, deploy commands, E2E runners, ticket systems, and
communication tools. This split keeps the reusable policy open-source-safe while
allowing each project to bind the core to its own workflow.

## Core vs profile

| Layer | Owns | Example |
| --- | --- | --- |
| Core | lifecycle, gates, reviewer contracts, evidence, progress, PR readiness concepts | R1-R5, empty open questions, dry-run first |
| Profile | local tools, repo conventions, labels, deploy/E2E commands, mirror format, communication surfaces | repository labels, staging command, E2E runner |

## Included profiles

- `profiles/example-api-ticket/profile.json` — open-source-safe example profile.

Projects should create their own private profiles for organization-specific
repositories, labels, ticket systems, deploy commands, communication channels,
and validation runners.

## Validation

```bash
python3 scripts/harness/validate_profile.py --root . --json
```

The validator ensures:

- required core files exist
- core does not leak obvious project-private terms
- profiles extend `policies/harness-core`
- R1-R5 gates are declared
- label discovery, communication ledger, and dry-run-first automation are present

## Adoption path

1. Copy or vendor the core policies.
2. Start with `profiles/example-api-ticket/profile.json` as a template.
3. Create a private project profile outside public source control if it contains
   internal repository names, ticket-system URLs, deploy commands, or channel
   references.
4. Run the validator in CI or before publishing profile changes.
