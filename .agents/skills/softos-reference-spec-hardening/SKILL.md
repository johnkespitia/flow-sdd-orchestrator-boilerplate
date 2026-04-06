---
name: softos-reference-spec-hardening
description: Use when a SoftOS spec is already decent or approved, but must be hardened into a 10/10 reference spec that an implementation agent can execute with minimal inference. Best for platform specs, roadmap-child specs, and critical feature specs that need executable surface inventory, algorithms, stop conditions, evidence contracts, and anti-hallucination closure.
---

# SoftOS Reference Spec Hardening

Use this skill when the goal is not merely to make a spec good or approvable, but to make it a stable execution reference for downstream agents.

Read first:

- `../softos-spec-definition-playbook/SKILL.md`
- `references/reference-spec-ladder.md`

Use this skill after the base spec is already coherent. Do not start here for raw ideation.

## Outcome

At the end, the spec should reach this bar:

- a competent implementation agent should not need to invent important behavior
- the spec should explain what must change, where to look first, how to advance, when to stop, and what evidence to produce
- the spec should survive handoff across multiple agents without semantic drift

## When to use

Use this skill when one or more of these are true:

- the spec already passed review/CI but still feels too abstract for execution
- the spec defines platform or persistence changes that will affect many child specs
- the user asks for a `10/10` spec or a reference spec
- the spec keeps requiring multiple clarification rounds before it feels executable
- the implementation repo is legacy-heavy and surface discovery must be governed tightly

## Core idea

A spec can be:

1. conceptually correct
2. approvable
3. implementation-ready
4. reference-grade

This skill is for the jump from 2/3 to 4.

## Hardening ladder

Apply these layers in order. Do not skip ahead unless the earlier layer is already explicit in the spec.

1. Confirm the governing decision
- architecture choice
- prohibited alternatives
- source of truth
- parity vs correction policy

2. Close execution surface
- executable inventory of write/read paths
- technical inventory of observed surfaces
- what is mandatory, deferred, and out of scope

3. Close the algorithm
- ordered steps
- per-table or per-flow algorithm
- sequencing constraints
- parent/child blocking rules

4. Close exception handling
- inconsistency taxonomy
- disposition matrix
- thresholds
- stop conditions
- rules for partial closure

5. Close evidence
- minimum evidence package
- where evidence must live
- what counts as persistent evidence
- how functional/E2E evidence links back to the spec

6. Re-run execution test
- ask whether an implementation agent could still make a material decision differently and claim compliance
- if yes, the spec is not yet reference-grade

## Mandatory sections for a reference-grade spec

Add these when missing:

- executable surface inventory
- technical observed inventory
- algorithm by table/flow/domain object
- disposition and threshold matrix
- stop conditions
- evidence package
- evidence delivery contract
- explicit relationship to existing E2E/UAT evidence
- definition of closure with allowed residual debt

## Rules

- Do not add vague prose to simulate rigor.
- Prefer tables, algorithms, and decision matrices over narrative.
- Do not say legacy flow unless the spec also says whether it is mandatory, deferred, or out of scope.
- Do not say acceptable threshold unless the threshold semantics are explicit.
- Do not say evidence required without defining the evidence package and delivery contract.
- If the spec touches operational journeys, connect it to existing E2E/UAT evidence explicitly.
- If the spec is platform/base, define how child specs must depend on it.

## Preferred review questions

Use these after each hardening pass:

1. Does the spec say what changes, or only what should become true?
2. Does it define the surface to inspect, or does it leave discovery fully open?
3. Does it define algorithmic order, or only end-state?
4. Does it define what blocks closure?
5. Does it define what evidence must exist and where it must be found?
6. Could two competent agents still implement materially different behavior and both claim compliance?

## Minimum validation

Run:

```bash
python3 ./flow spec review <spec-path>
python3 ./flow ci spec <spec-path>
```

But do not confuse passing governance with reference-grade maturity. Governance is necessary, not sufficient.

## Stop rule

The spec is not 10/10 if any of these remain true:

- an agent must infer the concrete surfaces to inspect
- an agent must invent the sequencing logic
- an agent must choose its own inconsistency policy
- an agent can close the work without a defined evidence package
- the user-facing or operator-facing journeys affected by the change are not tied to explicit evidence
