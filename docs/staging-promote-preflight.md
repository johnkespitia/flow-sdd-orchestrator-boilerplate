# Staging Promote Preflight

Spanish mirror: [docs/es/staging-promote-preflight.es.md](./es/staging-promote-preflight.es.md)

Source: `docs/staging-promote-preflight.md`  
Last updated: 2026-05-06

Use this playbook when promoting work to `staging` in SoftOS.

## The four gates

1. Local repo readiness
2. Remote source readiness
3. Workflow dispatch readiness
4. Environment rollout readiness

If any gate fails, the correct result is `promote blocked`.

## Minimum preflight

- changes committed
- source branch pushed
- dispatch runtime confirmed
- `gh` confirmed inside the `workspace` devcontainer
- auth confirmed in that runtime
- workflow inputs known
- rollout-sensitive migrations still gated

## Runtime rule

In this workspace, `gh` is expected to be installed in the devcontainer service `workspace`.

So:

- lack of `gh` on the host shell is not the relevant blocker
- the relevant blocker is missing auth or unusable workflow dispatch inside `workspace`

## Decision model

Only two outputs are valid:

- `promote dispatchable`
- `promote blocked`

## Important rule

Do not confuse:

- "implemented locally"

with

- "promotable to staging"

A staging promote is real only when the remote ref, dispatch mechanism, and rollout gate are all ready.
