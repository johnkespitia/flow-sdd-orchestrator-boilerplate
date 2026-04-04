---
name: softos-agent-playbook
description: Use when working inside a SoftOS workspace and the task touches specs, releases, CI, stack orchestration, or cross-repo behavior. This skill defines the default way an AI agent should operate SoftOS correctly.
---

# SoftOS Agent Playbook

Use this skill as the default operating guide for any non-trivial task in this workspace.

## Outcomes

- Specs remain the source of truth.
- `.flow/**` is treated as operational state, not canonical product intent.
- Cross-repo work stays routed through `workspace.config.json`.
- Releases, CI, and stack operations use `flow` commands before ad hoc scripts.

## Default workflow

1. Read the root spec first if the task touches system behavior, orchestration, or multiple repos.
2. Resolve repo/runtime context from `workspace.config.json`.
3. Prefer `flow` commands over direct file edits for lifecycle actions:
   - `flow spec review|approve`
   - `flow plan`
   - `flow workflow next-step|execute-feature|run`
   - `flow ci spec|repo|integration`
   - `flow release cut|promote|verify|publish`
   - `flow worktree list|clean`
   - `flow stack plan|apply`
4. When running workspace-managed toolchains from host, use:
   - `python3 ./flow workspace exec -- <cmd>`
   - `scripts/workspace_exec.sh <cmd>`
   - or commands that already delegate automatically such as `flow tessl`, `flow bmad`, `flow skills doctor|sync`, and `flow ci repo`
5. When running repo runtime commands, use:
   - `python3 ./flow repo exec <repo> -- <cmd>`
   - `python3 ./flow repo exec <repo> --workdir <slice-worktree> -- <cmd>` when the command must validate a materialized slice instead of the base checkout
   - not `workspace exec`, when the repo owns its own compose service
6. Only edit files covered by spec `targets`.
7. Treat `status: released` as terminal:
   - valid for strict CI and traceability
   - not valid for re-planning or re-execution
8. When a slice is governance, enforcement, minimal-change, or verification-only, prefer a compliance closeout over speculative expansion:
   - honor `surface_policy`
   - close with `minimum_valid_completion`
   - use `acceptable_evidence`
   - only escalate when there is a real technical blocker, not merely narrow scope

## Rules

- Root `specs/**` is canonical. Never let `.flow/state` override the spec.
- For implementation work, descend into the target repo only after reading the root spec.
- Use multi-slice governance at spec/planning level; do not try to force parallelism in the scheduler.
- When a repo already provides its own docker compose or CI pipeline, integrate it instead of duplicating it.
- If the slice does not require new surface area, do not reopen scope. Produce the minimum valid diff, enforcement, tests, or validated no-op evidence declared by the spec.

## Key patterns

### Release model

- `flow release cut|promote` is the operational release flow for approved feature specs.
- `flow release publish` is the OSS repo release flow:
  - semver
  - changelog
  - tag
  - optional GitHub Release

Use `flow release publish --dry-run --skip-github --json` before publishing.

### Stack model

- The workspace compose remains the control plane for `workspace` and shared services.
- Implementation repos may contribute their own compose file.
- If a repo declares or contains its own compose file, do not inject a duplicate service into `.devcontainer/docker-compose.yml`.

See:
- `docs/softos-agent-dev-handbook.md`
- `README.md`

### CI model

- Root CI governs specs and integration.
- Repo CI may be generic (`flow ci repo <repo>`) or delegated to a project workflow.
- Delegated project CI must be triggered only by SoftOS root CI, not directly by `push`/`pull_request`.

Use the specialized skill `softos-repo-ci-delegation` when implementing or modifying that pattern.

### Worktree hygiene model

- Worktrees under `.worktrees/**` are temporary operational artifacts, not permanent state.
- Preserve only active plan worktrees, worktrees with unintegrated changes, and worktrees explicitly retained for immediate reuse.
- Prefer `flow worktree list --json` and `flow worktree clean --stale --dry-run --json` before manual `git worktree remove`.

Use the specialized skill `softos-worktree-hygiene` when closing slices, cleaning `.worktrees/**`, or automating post-execution cleanup.

## Checks to prefer

```bash
python3 ./flow ci spec --all --json
python3 ./flow ci repo --all --json
python3 ./flow ci integration --profile smoke:ci-clean --auto-up --json
python3 ./flow release publish --dry-run --skip-github --json
```
