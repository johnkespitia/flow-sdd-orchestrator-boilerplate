# Independent Review Layer

Independent reviewers validate artifacts with fresh expert eyes. They must not
inherit builder chat history or undocumented rationale.

## R1 — Spec Review

Approves only if the spec is implementation-ready, scope is explicit, related
work is classified, validation is meaningful, and `Open Questions` is empty.

Verdicts: `APPROVE_SPEC`, `REQUEST_SPEC_CHANGES`, `BLOCK_SPEC_SCOPE`.

## R2 — Plan Review

Approves only if the plan maps to the spec, write scopes are bounded, tests and
rollout are scheduled, and no unresolved spec questions remain.

Verdicts: `APPROVE_PLAN`, `REQUEST_PLAN_CHANGES`, `BLOCK_PLAN_UNCLEAR_SCOPE`.

## R3 — Code Review

Required for runtime, data, contract, generated-doc, or test diffs. Passing
local tests or structural workflow verification is not a substitute.

Verdicts: `APPROVE_CODE`, `REQUEST_CODE_CHANGES`, `BLOCK_CODE_SCOPE_OR_RISK`.

## R4 — Validation / Deploy Review

Approves only if validation evidence proves behavior for the correct revision or
explicitly documents non-applicability with accepted compensating evidence.

Verdicts: `APPROVE_VALIDATION`, `REQUEST_MORE_VALIDATION`, `BLOCK_ROLLOUT`.

## R5 — PR / Commit Readiness Review

Approves branch/commit/PR metadata before PR creation or ready-for-review.
Profiles supply repo-specific labels, title conventions, reviewer rules, and
expected checks.

Verdicts: `APPROVE_PR_CREATE`, `REQUEST_PR_CHANGES`, `BLOCK_PR_PUBLISHING`.
