# Changelog

All notable changes to this project will be documented in this file.

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
