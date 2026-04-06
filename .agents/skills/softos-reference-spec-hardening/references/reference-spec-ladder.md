# Reference Spec Ladder

Use this reference when a spec feels good enough but not yet stable enough for agent execution.

## Maturity ladder

### Level 1. Idea spec

The spec explains the problem and desired outcome, but leaves major execution choices open.

Typical symptoms:

- broad scope language
- little or no explicit exclusions
- weak evidence section
- no clear algorithm

### Level 2. Approvable spec

The spec can pass governance review and looks coherent, but still leaves meaningful execution choices to the implementer.

Typical symptoms:

- architecture is clear
- acceptance criteria exist
- tests are named
- but surfaces, thresholds, and evidence delivery are still under-specified

### Level 3. Implementation-ready spec

The spec is bounded and concrete enough that a downstream agent can implement it with moderate discovery work.

Typical symptoms:

- scope and exclusions are solid
- business rules are explicit
- main flows are clear
- there is some evidence strategy

Remaining gap:

- discovery is still partially implicit
- exception handling may still be under-specified

### Level 4. Reference spec

The spec is stable enough to guide execution across agents with minimal semantic drift.

Expected properties:

- governing decision is explicit
- execution surface is enumerated
- technical starting points are named
- algorithm/order is explicit
- exceptions are classified and dispositioned
- thresholds and stop conditions are explicit
- evidence package and evidence delivery are explicit
- functional/E2E relationship is explicit
- residual debt is bounded and named

## What to add when moving from implementation-ready to reference spec

### Add executable inventory

Not just flows affected, but:

- write paths
- read paths
- technical surfaces
- mandatory vs deferred vs out of scope

### Add algorithm

Not just materialize tenant, but:

- ordered steps
- per-table/per-flow algorithm
- parent-child dependency rules

### Add exception policy

Not just handle inconsistencies, but:

- classification
- disposition
- thresholds
- stop conditions
- partial closure rules

### Add evidence contract

Not just provide evidence, but:

- required artifacts
- storage/location expectations
- linkability from spec closure

## Quick execution test

A spec is reference-grade only if the answer to all these is yes:

- Can the agent identify where to start inspecting the system?
- Can the agent tell what must change first?
- Can the agent tell what must not change?
- Can the agent tell what blocks closure?
- Can the agent tell what exact evidence package must exist?
- Can the agent execute without inventing policy?
