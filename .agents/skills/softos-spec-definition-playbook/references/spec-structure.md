# Spec Structure

Use this reference when drafting or rewriting a SoftOS spec so the document matches the role it plays in the workspace.

## Placement rules

- `specs/000-foundation/**`: operating model, governance, platform guardrails, or root orchestration rules
- `specs/domains/**`: stable concepts, shared vocabulary, entities, or cross-feature contracts
- `specs/features/**`: executable features, waves, hardening, reliability, and delivery slices

Choose the folder first. The folder determines how concrete the spec must be.

## Frontmatter

Include at minimum:

- `name`
- `description`
- `status`
- `owner`
- `targets`

Add when relevant:

- `depends_on`
- `infra_targets`
- `required_runtimes`
- any other field already used by adjacent specs and needed for execution

Rules:

- `targets` must point to real paths
- `depends_on` must include applicable foundation or domain specs for new feature work, unless the body justifies exclusion
- do not invent frontmatter fields that no tool or reviewer will use

## Recommended body order

1. Title
2. Objective
3. Context
4. Problem to solve
5. Scope
6. Out of scope
7. Affected repos or surfaces
8. Contracts, invariants, or behavior requirements
9. Acceptance criteria
10. Evidence or verification expectations

Add extra sections only when they reduce ambiguity.

## Additional sections by spec family

### Foundation specs

Prefer:

- operating rules
- governance constraints
- architecture decisions
- prohibited alternatives
- orchestration contracts
- downstream impact on feature specs

### Domain specs

Prefer:

- canonical terminology
- entity or lifecycle definitions
- cross-feature invariants
- boundaries between concepts
- stable contract definitions

### Feature specs

Prefer:

- exact included flows
- explicit exclusions
- affected commands, routes, tables, files, or jobs
- side effects
- observable outputs
- required evidence for approval and release
- explicit slice closeout rules when a slice is governance, enforcement, minimal-change, or verification-only
- `## Verification Matrix` when smoke, integration, api-contract, e2e, or release-blocking checks are part of the contract

## Verification Matrix contract

Use `## Verification Matrix` when the spec needs tests beyond repo-local `[@test]` references.

Each profile should declare:

- `name`
- `level`
- `command`
- `blocking_on`

Add when relevant:

- `environments`
- `notes`

Rules:

- `Verification Matrix` is for transversal or stage-blocking checks.
- `[@test]` remains the contract for repo-local tests and linked test files.
- Commands should be executable from the workspace root.
- If a profile blocks release, its command must be stable enough to run from `flow release verify`.

## Slice Breakdown contract

For `schema_version: 3` specs, every slice should be concrete enough for a downstream executor to act without reopening scope.

Always include:

- `name`
- `targets`
- `hot_area`
- `depends_on`

Add explicitly when relevant:

- `slice_mode`: `implementation-heavy`, `refactor`, `governance`, `enforcement`, `minimal-change`, or `verification-only`
- `surface_policy`: `required`, `optional`, or `forbidden`
- `minimum_valid_completion`
- `validated_noop_allowed`
- `acceptable_evidence`

Rules:

- If `slice_mode` is `governance`, `enforcement`, `minimal-change`, or `verification-only`, do not leave closeout implicit.
- If `surface_policy` is `optional` or `forbidden`, define the minimum acceptable outcome and the evidence required to close the slice.
- If a slice can validly end without new endpoints, routes, or UI surface, say so explicitly.

### Hardening or reliability specs

Prefer:

- measured risk
- thresholds or failure conditions
- rollout expectations
- rollback expectations
- proof required to call the risk reduced

## Strong writing patterns

- Prefer exact observable behavior over aspiration.
- Prefer concrete commands and files over generic references to "the system".
- Prefer tables or bullet inventories for permissions, parity decisions, and side effects.
- Prefer explicit exclusions over silence.
- Prefer "what must remain true" before "how to implement it".

## Smells to remove

These phrases usually mean the spec is still too weak:

- "preserve existing behavior" without describing that behavior
- "as needed"
- "if applicable" without conditions
- "or equivalent"
- "follow current logic"
- "handle edge cases appropriately"
- "update anything necessary"

Replace vague phrases with explicit contracts, inventories, or stop conditions.
