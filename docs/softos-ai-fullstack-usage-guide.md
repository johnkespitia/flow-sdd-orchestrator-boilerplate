# How AI Understands and Uses SoftOS at Full Power

Spanish mirror: [docs/es/softos-ai-fullstack-usage-guide.es.md](./es/softos-ai-fullstack-usage-guide.es.md)

Source: `docs/softos-ai-fullstack-usage-guide.md`  
Last updated: 2026-05-07

This document explains how an AI agent should reason, execute, and validate work in SoftOS to maximize reliability and throughput.

## 1. AI mental model

SoftOS is spec-driven orchestration, not ad-hoc coding.

The AI should treat:

- `specs/**` as source of truth.
- `flow` as the orchestration control plane.
- CI reports and release evidence as completion criteria.

## 2. Correct execution order

1. Read relevant spec first.
2. Resolve target repos and runtime context.
3. Load skill context for the repo.
4. Implement only inside declared targets.
5. Run required validations.
6. Produce evidence and close loop.

## 3. AI contract for safe changes

1. Never infer major scope expansion without spec update.
2. Never mark done without CI/spec evidence.
3. Never treat `.flow/**` as source of truth over `specs/**`.
4. Prefer minimal deterministic diffs for each slice.

## 4. High-leverage AI workflow

1. **Spec parse**: extract goals, non-goals, targets, stop conditions.
2. **Surface mapping**: map every intended edit to target paths.
3. **Implementation**: apply narrow edits.
4. **Validation**: run `flow` CI gates and repo-specific tests.
5. **Evidence capture**: keep command outputs and artifacts linked to slice.
6. **Release readiness**: verify preflight constraints before promotion.

## 5. Multi-repo reasoning

AI should avoid cross-repo leakage by default.

- Changes in repo A must not silently modify repo B.
- Shared behavior must be represented in root specs first.
- Runtime/tooling commands must execute in the correct repo service.

## 6. CI-first completion logic

AI completion criteria should include:

- spec guard passes
- drift check passes
- contract verify passes
- repo CI passes where required
- no unresolved gating blockers

## 7. Promotion discipline

Before staging promotion, AI must verify:

- remote source ref readiness
- workflow dispatch readiness
- gateway/runtime auth availability
- rollout-sensitive migrations still gated

Output is binary:

- `promote dispatchable`
- `promote blocked`

## 8. Documentation intelligence

AI should keep docs executable and current:

- update ops docs with behavior changes
- maintain EN canonical + ES mirror policy
- ensure cross-links and metadata are present
- prefer concise, operationally verifiable language

## 9. Memory usage policy

If memory tooling is enabled, AI should use memory as consultive context only.

- memory helps with recall and continuity
- memory never overrides specs, CI evidence, or release contracts

## 10. Full-power mode checklist for AI

- spec-first planning complete
- target surfaces bounded
- runtime/skills context loaded
- implementation applied with minimal drift
- CI gates executed and green
- release preflight evaluated
- documentation updated and mirrored
- final report includes evidence and residual risks
