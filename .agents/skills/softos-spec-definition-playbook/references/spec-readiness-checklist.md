# Spec Readiness Checklist

Use this checklist before treating a SoftOS spec as ready for review, approval, planning, or slicing.

## Core readiness test

Ask:

1. Can an implementation agent identify the exact in-scope files, flows, or commands?
2. Can the agent identify which observable behavior must remain identical?
3. Can the agent identify which behavior is intentionally changing?
4. Can the agent identify required side effects and forbidden side effects?
5. Can the agent identify who is allowed to trigger the flow?
6. Can the agent identify the evidence required to prove completion?
7. Can the agent identify when to stop because the work exceeds scope?
8. Can the agent identify which foundations and domains the spec depends on?

If any answer is "not from the spec alone", the spec is incomplete.

## Completion checklist

- [ ] The spec is in the correct folder: foundation, domain, or feature.
- [ ] `targets` map to real files or directories.
- [ ] `depends_on` includes applicable foundation or domain specs, or the omission is justified.
- [ ] Scope is explicit.
- [ ] Out-of-scope work is explicit.
- [ ] Invariants or contract rules are explicit.
- [ ] Observable outputs are explicit.
- [ ] Errors, edge cases, or prohibitions are explicit when relevant.
- [ ] Evidence for review or approval is explicit.
- [ ] Acceptance criteria are testable.
- [ ] Stop conditions are explicit when scope could expand during implementation.

## Strong validation pattern

Run the two-implementer test:

- If two competent agents could implement different behavior and both argue they followed the spec, tighten the spec.

## Preferred remediation

When a spec is weak, do not add more generic prose. Add one of:

- an inclusion inventory
- an exclusion inventory
- a decision table
- a permission matrix
- a side-effects matrix
- a command or transport contract
- a parity-vs-bug decision table
- explicit evidence requirements
