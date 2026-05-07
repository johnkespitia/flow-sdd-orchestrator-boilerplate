# Harness Core Gates

## G0 — Intake Captured

Pass when the source of truth, user-visible goal, suspected surfaces, and
unknowns are recorded.

## G1 — Research and Cluster Gate

Pass when related tickets, PRs, specs, owner context, and overlapping code or
contracts are classified as duplicate, superseding, dependency, semantic
conflict, safe parallel, or unrelated.

Fail when duplicate/superseding/semantic-conflict work remains unresolved.

## G2 — Planning Gate

Pass when the spec is internally consistent, scope is explicit, rollout and
validation are planned, and `Open Questions` is empty or represented as `None`.

Fail when any unresolved question remains in the spec.

## G3 — Implementation Gate

Pass when branch/write ownership is clear, generated artifacts are handled, and
R3 code review has approved the diff for implementation changes.

Fail when implementation is complete but no R3 artifact exists.

## G4 — Validation Gate

Pass when validation evidence proves the changed behavior and regressions, E2E
is present or explicitly not applicable, environment/revision are documented,
and R4 approves validation/deploy evidence.

## G5 — PR / Commit Readiness Gate

Pass when branch, commit, PR title/body, labels, reviewers, linked artifacts,
and expected checks are validated by the active profile.

## G6 — Closeout Gate

Pass when PR/ticket/channel state reflects reality, follow-ups are linked,
artifacts are complete, and lessons/memory are captured.
