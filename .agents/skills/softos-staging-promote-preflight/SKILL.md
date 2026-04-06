---
name: softos-staging-promote-preflight
description: Use when promoting a spec or repo change to staging in SoftOS and you need a hard preflight before dispatching workflows or enabling environment-specific rollout steps. Covers source_ref readiness, auth, workflow dispatch, candidate migrations, and binary promote outcomes.
---

# SoftOS Staging Promote Preflight

Use this skill when a user asks to promote work to `staging` and the promote depends on more than local code being correct.

This skill exists to prevent a common failure mode:

- implementation is ready locally
- CI is green
- but the promote still fails because the source branch is not published, auth is missing, the wrong shell is used, or rollout-sensitive migrations are enabled too early

Read first:

- `../softos-agent-playbook/SKILL.md`
- `../softos-release-manager/SKILL.md`
- `../softos-schema-hardening-gates/SKILL.md`
- `../../../docs/staging-promote-preflight.md`

## Workspace assumption

In this workspace, `gh` is expected to be installed inside the devcontainer service `workspace`.

Treat this as the default operating assumption:

- `gh` should be checked and used inside `workspace`
- missing `gh` on the macOS host is not itself a staging-promote blocker
- the real preflight question is whether `gh` is authenticated and usable in `workspace`

Do not report "`gh` is missing" unless it is missing from the actual `workspace` runtime being used for dispatch.

## Outcome

At the end:

- the agent knows whether promote is actually dispatchable
- the decision is binary:
  - `promote dispatchable`
  - `promote blocked`
- rollout-sensitive steps such as schema hardening are not activated accidentally
- the handoff distinguishes clearly between:
  - local readiness
  - remote source readiness
  - workflow dispatch readiness
  - environment rollout readiness

## When to use

Use this skill when one or more of these are true:

- the user asks to promote to `staging`
- the repo uses GitHub Actions or another remote workflow to promote
- a `source_ref` must exist remotely
- the rollout includes environment-gated migrations or commands
- the agent is working from a devcontainer or nested repo and host-vs-container execution matters

## Core model

Treat staging promote as four separate gates:

1. local repo readiness
2. remote source readiness
3. workflow dispatch readiness
4. environment rollout readiness

Do not collapse them into one vague "ready to promote" statement.

## Required preflight

Before dispatching a staging promote, verify all of these:

### 1. Local repo readiness

- the target repo changes are committed
- the intended branch exists locally
- there is no confusion about whether the code lives only in working copy or in a publishable ref

### 2. Remote source readiness

- the intended `source_ref` exists in GitHub
- the branch actually contains the code that should be promoted
- the promote workflow will read from that ref, not from an unrelated default branch

### 3. Workflow dispatch readiness

- execution is happening in the correct runtime context, usually the `workspace` container rather than the host shell
- `gh` or equivalent dispatcher is available in that runtime
- auth is valid in that same runtime
- the target workflow exists
- required inputs are known:
  - `environment`
  - `source_ref`
  - `version`
  - `requested_by`
  - migration flags or equivalents

### 4. Environment rollout readiness

- if the release includes gated schema hardening, candidate migrations remain outside the automatic path until the environment gate passes
- any required verify command for `staging` is known in advance
- the agent can say exactly whether the environment step is:
  - runnable now
  - blocked by lack of access
  - blocked by gate failure

## Binary outcomes

Only these outcomes are valid:

### A. Promote dispatchable

Meaning:

- `source_ref` exists remotely
- workflow auth is valid
- workflow inputs are known
- dispatch can happen now

### B. Promote blocked

Meaning at least one of these is false:

- branch/ref not published
- auth not valid in the executing runtime
- workflow unavailable
- environment access unavailable
- rollout gate not yet satisfied

Do not hide a blocked promote behind "everything is ready except...".

## Preferred workflow

1. Identify the repo being promoted.
2. Confirm whether the relevant code is committed.
3. Confirm whether the branch is pushed and usable as `source_ref`.
4. Confirm runtime context for dispatch.
5. Confirm `gh` and auth in that runtime.
6. Confirm workflow name and required inputs.
7. If schema hardening is involved, confirm candidate-vs-active migration state.
8. Only then decide whether the promote can be dispatched.

## Review questions

Ask these before claiming a staging promote is possible:

1. Does the code to promote exist in a remote branch?
2. Is the branch the one the workflow will actually read?
3. Is dispatch happening from the correct runtime context?
4. Is `gh` installed and auth valid there?
5. If migrations run in staging, are rollout-sensitive migrations still gated correctly?
6. Can the agent prove the next step is dispatch, not more local setup?

## Minimum evidence

The handoff should make these explicit:

- repo/branch being promoted
- whether `source_ref` exists remotely
- whether dispatch auth is valid
- workflow to be triggered
- whether staging guardrails are runnable
- decision:
  - `promote dispatchable`
  - `promote blocked`

## Stop rule

The promote flow is not correct if any of these remain true:

- the code exists only in local working copy
- the branch is not pushed remotely
- the workflow is ready in theory but cannot be dispatched from the real runtime
- the report says "promote to staging" while rollout-sensitive migrations would still auto-run without a gate
