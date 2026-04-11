# Changelog

All notable changes to this project will be documented in this file.

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
