# SoftOS Harness Core

SoftOS Harness Core is the reusable, project-neutral policy pack for ticket and
change delivery. It defines the lifecycle, gates, evidence, review layers,
progress visibility, communication, PR readiness, and dry-run-first automation
without assuming any one company's repositories, labels, staging system, or chat
tools.

Use a project profile to bind this core to a real workspace. Profiles own repo
labels, ticket systems, PR conventions, staging/deploy commands, E2E runners,
repo-local planning formats, and communication surfaces.

## Core files

- `lifecycle.md` — generic intake-to-closeout flow.
- `gates.md` — gate contracts and pass/fail rules.
- `independent-review.md` — R1/R2/R3/R4/R5 reviewer layer.
- `evidence.md` — evidence registry and stale-evidence rules.
- `progress-and-communication.md` — progress/retry transparency and hypercommunication.
- `pr-readiness.md` — branch/commit/PR readiness contract.
- `automation.md` — dry-run-first automation model.

## Design rule

Core policies must stay free of project-specific names, links, credentials,
private ticket keys, repository names, and environment URLs. Put those in
`profiles/<profile-id>/profile.json` or profile documentation.
