# Changelog

All notable changes to this project will be documented in this file.

## v0.14.0 - 2026-09-09

### Added

- add ACP-first executor transport

## v0.13.0 - 2026-09-08

### Added

- integrate Engram and Graphify

## v0.12.1 - 2026-09-07

### Changed

- Merge pull request #28 from johnkespitia/fix/workspace-user-tooling-home-ownership

### Fixed

- prepare workspace user tooling directories

### Docs

- align runtime ownership spec with tooling dirs

## v0.12.0 - 2026-09-07

### Added

- implement coding execution runtime resource pools
- harden deterministic repository verification (#14)
- add agent executor adapters
- add bounded agent process execution
- add agent registry and diagnostics
- add usage cost harness

### Changed

- Merge pull request #27 from johnkespitia/docs/execution-runtime-compatibility-boundary
- Fix OpenCode Go auth detection
- Merge pull request #26 from johnkespitia/docs/execution-runtime-compatibility-boundary
- Merge pull request #22 from johnkespitia/feat/coding-runtime-resource-pools-v1
- Merge remote-tracking branch 'origin/main' into feat/coding-runtime-resource-pools-v1
- Merge pull request #25 from johnkespitia/fix/spec-guard-approved-base-coverage
- Merge remote-tracking branch 'origin/main' into feat/coding-runtime-resource-pools-v1
- Merge pull request #24 from johnkespitia/fix/spec-guard-approved-base-coverage
- Merge remote-tracking branch 'origin/main' into feat/coding-runtime-resource-pools-v1
- Merge pull request #23 from johnkespitia/fix/spec-guard-approved-base-coverage
- Merge pull request #21 from johnkespitia/chore/coding-execution-runtime-v1-governance-clean
- Merge pull request #20 from johnkespitia/chore/coding-execution-runtime-v1-spec-clean
- Merge pull request #19 from johnkespitia/feat/host-repo-exec-routing-alignment-clean
- align host repo exec routing
- Merge pull request #18 from johnkespitia/fix/slice-start-runtime-path-rebase-clean
- Merge pull request #17 from johnkespitia/fix/staged-spec-guard-approved-coverage
- preserve staged spec guard coverage before reinstall
- wire SoftOS OpenCode worker wrapper (#15)
- Merge pull request #13 from johnkespitia/chore/orchestration-v0-governance
- defer specs with unresolved targets
- Merge pull request #12 from johnkespitia/fix/runtime-user-ownership
- Merge pull request #11 from johnkespitia/feat/opencode-workdir-isolation
- Merge pull request #10 from johnkespitia/feat/agent-executors-mainline
- approve agent executors
- Merge pull request #9 from johnkespitia/chore/upstream-workspace-harness
- enforce workspace-only host execution
- Merge pull request #8 from johnkespitia/codex/usage-cost-harness
- sanitize private leak terms
- Merge pull request #7 from johnkespitia/chore/bmad-multiagent-contract-upstream
- enforce multi-agent ownership handoff and gates

### Fixed

- route dynamic OpenCode models through process args
- cover approved specs in drift check
- allow shared approved spec coverage
- allow approved base specs for changed guard
- avoid false positive in secret scan
- rebase slice start runtime paths
- rebase slice start runtime paths
- run workspace operations as development user
- enforce agent worktree isolation
- run workspace commands as workspace user
- allow host execution on CI runners

### Docs

- document execution runtime compatibility boundary
- document execution runtime compatibility boundary
- add Spanish execution resources mirror
- align coding runtime prospective target ownership
- align coding runtime approval and verification wording
- refine coding execution runtime v1 boundary
- refine coding execution runtime boundary
- add coding execution runtime v1 spec
- add deterministic repository verification hardening spec (#16)
- add Spanish OpenCode executor mirror
- add orchestration v0 governance and opencode executor notes
- link Spanish agent executors mirror
- add Spanish agent executors mirror

## v0.11.0 - 2026-04-29

### Added

- add optional autoskills integration and update tooling docs

## v0.10.3 - 2026-04-17

### Added

- enforce scope drift before cut

## v0.10.2 - 2026-04-17

### Added

- add handoff packages

## v0.10.1 - 2026-04-16

### Added

- add spec evidence bundles

## v0.10.0 - 2026-04-16

### Added

- add human-gated runner mode

## v0.9.10 - 2026-04-16

### Fixed

- support standalone docker-compose

## v0.9.9 - 2026-04-16

### Added

- add central stage checks

## v0.9.8 - 2026-04-16

### Added

- formalize plan approval gate

## v0.9.7 - 2026-04-16

### Added

- formalize spec approval gate

## v0.9.6 - 2026-04-11

### Added

- add autonomous memory hooks

## v0.9.5 - 2026-04-11

### Added

- add optional memory smoke workflow

## v0.9.4 - 2026-04-11

### Added

- add advisory memory prune

## v0.9.3 - 2026-04-11

### Added

- add guarded import and backup

## v0.9.2 - 2026-04-11

### Added

- structure search and export memory

## v0.9.1 - 2026-04-11

### Added

- activate Engram MCP clients

## v0.9.0 - 2026-04-11

### Added

- scope Engram during bootstrap

## v0.8.0 - 2026-04-11

### Added

- add flow memory wrappers

## v0.7.0 - 2026-04-11

### Added

- install Engram in devcontainer

## v0.6.0 - 2026-04-11

### Added

- add optional Engram capability

### Docs

- add v0.5.1 release notes
- improve v0.5.0 release notes

## v0.5.1 - 2026-04-10

### Docs

- improve v0.5.0 release notes

## v0.5.0 - 2026-04-10

### Added

- Automate claim-to-plan execution in the gateway so accepted claims transition into SDLC planning without manual operator steps.
- Add autonomous slave intake polling to continuously discover new remote work and reduce idle time between claim cycles.

### Changed

- Harden the remote slave gateway workflow with safer claim lifecycle transitions and clearer operator-facing behavior.
- Introduce a remote gateway slave intake bridge to improve handoff reliability between gateway-side intake and slave-side execution.
- Improve end-to-end intake orchestration so remote claim processing is more predictable under autonomous operation.

## v0.4.10 - 2026-04-09

### Changed

- Add portable master gateway deployment baseline

## v0.4.9 - 2026-04-06

### Changed

- Add staging promote hardening playbooks

## v0.4.8 - 2026-04-06

### Changed

- Ignore runtime-only golang skill
- Add reference spec hardening skill

## v0.4.7 - 2026-04-05

### Changed

- Auto-clean stale worktrees after closeout

## v0.4.6 - 2026-04-04

### Changed

- Automate worktree cleanup lifecycle

## v0.4.5 - 2026-04-04

### Changed

- Harden release promotion contracts
- Fix README CI badge
- Add README views badge

## v0.4.4 - 2026-04-03

### Added

- add transversal verification matrix

## v0.4.3 - 2026-04-03

### Fixed

- normalize GitHub auth and terminal promotion policy

## v0.4.2 - 2026-04-03

### Added

- isolate repo runtime commands to slice worktrees

## v0.4.1 - 2026-04-03

### Added

- route repo runtime commands by service
- fail fast on stable-surface drift

### Fixed

- align bootstrap governance surfaces

## v0.4.0 - 2026-04-03

### Added

- add canonical workspace exec entrypoint
- add SoftOS spec definition playbook
- add reusable PR promotion deploy patterns

## v0.3.0 - 2026-03-31

### Added

- add reusable PR-promotion deployment patterns

### Fixed

- resolve worktree root inspection path

### Docs

- cover reusable PR promotion templates

## v0.2.0 - 2026-03-29

### Added

- propagate agent context to derived workspaces
- add SoftOS release manager skill
- add SoftOS operating playbooks
- delegate repo pipelines from root workflow
- include project compose files in workspace stack
- automate changelog and repo publishing

### Fixed

- allow dry-run without remote tag check

### Docs

- add Cursor and OpenCode SoftOS context
- add v0.1.2 release notes

## v0.1.2 - 2026-03-29

Release focused on operational closure, release-state consistency, and stronger orchestration governance.

### Added

- Persistent global lock coordination across workflow runs.
- Program-closure evidence matrix and retention regression coverage for `.flow/reports/**`.
- Gateway comment feedback coverage for `comment_added` and central secrets-source tests.

### Changed

- Promoted core specs to terminal `released` status when they reached verified release state:
  - `softos-program-closure-and-operational-readiness`
  - `softos-multiagent-concurrency-and-locking`
  - `softos-autonomous-sdlc-execution-engine`
  - `softos-quality-gates-traceability-and-risk`
- Release promotion now aligns operational state and spec frontmatter to `status: released`.
- `flow workflow next-step`, `flow plan`, `flow infra`, and strict spec CI now treat `released` as a valid terminal state.
- `flow release verify` now checks remote-tracking refs correctly instead of relying on raw SHA lookup.
- Dashboard/reporting flow gained stronger operational filtering and CI contract coverage.

### Fixed

- Spec selection in changed-only CI no longer treats `templates/*.spec.md` as live specs.
- CI command capture now handles missing executables without crashing with a traceback.
- Program-closure drift/spec evidence is aligned so closure updates do not fail changed-surface CI checks.

## v0.1.0 - 2026-03-28

First public open-source release of the SoftOS SDD Orchestrator Boilerplate.

### Added

- Master/slave bootstrap profiles with remote gateway wiring for developer runners.
- OSS community baseline files:
  - `SECURITY.md`
  - `CONTRIBUTING.md`
  - `CODE_OF_CONDUCT.md`
- Program closure deliverables across workflow/gateway hardening waves (A-D).

### Changed

- CI workflows now force JavaScript actions to Node 24 to stay ahead of GitHub runner deprecations.
- README branding and structure updated to:
  - `SoftOS SDD Orchestrator Boilerplate`
  - clearer quick navigation and OSS entrypoints.

### Notes

- This release is tagged from `main` and intended as the first reusable OSS baseline.
