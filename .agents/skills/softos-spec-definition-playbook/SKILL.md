---
name: softos-spec-definition-playbook
description: Use when creating, refining, reviewing, or hardening SoftOS specs so they are executable, bounded by real targets, and aligned with foundations, domains, runtime context, and CI evidence. Applies to foundation, domain, feature, and hardening specs.
---

# SoftOS Spec Definition Playbook

Use this skill when the task is to create a new spec, rewrite a weak spec, or review whether a spec is truly ready for planning, slicing, and execution.

## Outcomes

- The spec is the source of truth for behavior, not a loose implementation hint.
- `targets` point to real files or directories in the workspace routing model.
- `depends_on` reflects real foundation and domain dependencies, or the omission is justified in the body.
- A downstream agent can determine scope, invariants, observable outputs, and stop conditions without reverse-engineering code.
- The spec defines the evidence required to approve, implement, and verify the work.
- Slices that only preserve or enforce a contract declare an explicit minimum valid closeout instead of leaving the executor to guess whether a no-op or tests-only result is acceptable.

## Default workflow

1. Read the nearest `AGENTS.md` plus parent `AGENTS.md` files first.
2. Read the relevant root specs before writing anything:
   - `specs/000-foundation/**` for operating rules
   - `specs/domains/**` for vocabulary and stable contracts
   - sibling specs in the same folder for local conventions
3. Classify the spec correctly:
   - `specs/000-foundation/**` for operating model or platform guardrails
   - `specs/domains/**` for stable language, entities, and cross-feature contracts
   - `specs/features/**` for executable feature work, waves, or hardening
4. Ground the spec in current reality:
   - current specs
   - current code and docs
   - current commands and workflows
   - existing tests and evidence expectations
5. Resolve affected repos from `targets`, then inspect `workspace.config.json` and runtime context if the spec reaches into a project repo.
6. Define the contract before the implementation:
   - objective
   - scope and exclusions
   - actors
   - invariants
   - observable behavior
   - side effects
   - evidence and gates
   - for each slice, whether visible surface expansion is required, optional, or forbidden
   - for narrow governance slices, the minimum valid completion and whether a validated no-op is acceptable
7. Add anti-hallucination guardrails:
   - exact inclusions
   - exact exclusions
   - parity vs intentional change
   - stop conditions
8. Run a final readiness review before treating the spec as ready for `flow spec review`, planning, or slicing.

## SoftOS-specific rules

- Root `specs/**` is canonical. Never let `.flow/**` define product behavior.
- Any new feature spec must explicitly consider applicable foundation specs and domain specs through `depends_on` or a justified exclusion in the body.
- Do not write `targets` as placeholders. They must map to real roots allowed by the workspace routing model.
- If the spec changes behavior, update the spec in the same change; do not rely on later cleanup.
- If a repo is implicated by `targets`, resolve its runtime and skill context before finalizing implementation detail.
- If current behavior must be preserved, describe the preserved behavior explicitly.
- If current behavior is wrong, say whether to preserve, correct, or defer it.
- If strict verification will matter, define the command or evidence expected for approval.
- If a slice is governance, enforcement, minimal-change, or verification-only, declare the closeout contract explicitly:
  - `slice_mode`
  - `surface_policy`
  - `minimum_valid_completion`
  - `validated_noop_allowed`
  - `acceptable_evidence`

## Minimum contract for every strong spec

Always include:

- frontmatter with `name`, `description`, `status`, `owner`, `targets`
- `depends_on` whenever foundations or domains apply
- clear objective
- context grounded in the current workspace
- problem statement
- scope
- out of scope
- affected repos or target surfaces
- business, platform, or workflow invariants
- required outputs or externally visible behavior
- errors, edge cases, and prohibitions where relevant
- approval or verification evidence
- acceptance criteria

Include when relevant:

- actor/permission matrix
- transport or command contract
- input/output shape
- side-effects matrix
- parity-vs-bug decision table
- rollout or rollback expectations
- slice or implementation breakdown
- explicit stop conditions
- explicit slice closeout contract when the work may end in tests, enforcement, or validated no-op

## Repo and runtime grounding

When `targets` point into `../../<repo>/**`:

1. Resolve the repo from the target path.
2. Read `workspace.config.json` for repo metadata.
3. If needed, load runtime context:

```bash
python3 ./flow skills context --repo <repo> --json
```

Use the runtime context to make the spec technically credible, but do not let runtime detail replace the product or orchestration contract in the root spec.

## Anti-hallucination standard

A spec is weak if an implementation agent still has to guess:

- which files, methods, commands, or flows are in scope
- which behavior is intentionally changing
- which behavior must stay identical
- who can trigger the flow
- what evidence proves the work is done
- whether an API, command, or side effect is required, optional, or forbidden
- whether a slice may close without new routes or UI surface because the valid outcome is enforcement, verification, or contract preservation
- when the work must stop because it crosses scope

If two competent agents could implement materially different behavior and both claim compliance, tighten the spec.

## Preferred checks

```bash
python3 ./flow spec review <spec-path>
python3 ./flow ci spec <spec-path>
```

Use broader validation when the change touches multiple specs or system contracts:

```bash
python3 ./flow ci spec --all --json
```

## When to read references

- For the canonical structure and section selection rules, read [references/spec-structure.md](references/spec-structure.md).
- For the readiness and anti-hallucination review, read [references/spec-readiness-checklist.md](references/spec-readiness-checklist.md).
