# Harness Core Lifecycle

## Purpose

Provide a generic lifecycle for ambiguous, multi-step, review-sensitive work.
The lifecycle is artifact-driven: each phase produces evidence that the next
phase can consume without relying on chat history.

## Phases

0. Intake
1. Triage
2. Research
3. Cluster / collision review
4. Contract, dependency, and rollout analysis
5. Planning and spec
6. Approval gate
7. Implementation
8. Validation
9. PR / commit readiness
10. PR / review / communication
11. Release / rollout
12. Closeout and memory

## Operating rules

- Research precedes planning; planning precedes implementation.
- Related work must be classified before implementation starts.
- Draft specs may contain open questions; approved specs may not.
- Reviews consume artifacts and evidence, not undocumented builder rationale.
- Validation proves behavior, not only deploy success.
- Communication surfaces should reflect current state.
- Automation starts in dry-run mode until outputs are trusted.

## Lifecycle outputs

A profile may rename or route artifacts, but the semantic outputs should remain:

- intake record
- research pack
- related-work cluster
- contract/dependency matrix
- implementation-ready spec
- independent review artifacts
- validation evidence
- PR readiness pack
- communication ledger
- closeout/memory summary
