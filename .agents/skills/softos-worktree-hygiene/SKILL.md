---
name: softos-worktree-hygiene
description: Use when closing slices, cleaning `.worktrees/**`, reviewing stale worktrees, or automating operational cleanup after a SoftOS execution. This skill standardizes how to inventory, preserve, and remove worktrees safely.
---

# SoftOS Worktree Hygiene

Use this skill when a SoftOS workspace has accumulated linked worktrees and the goal is to close or clean them safely.

## Outcomes

- Active worktrees referenced by current plans are preserved by default.
- Dirty worktrees are never removed silently.
- Closed or orphan worktrees are removed through `flow worktree clean`, not by deleting directories manually.
- `git worktree prune` runs as part of the cleanup flow.

## Default workflow

1. Inventory current worktrees:

```bash
python3 ./flow worktree list --json
```

2. Review only stale-cleanable worktrees:

```bash
python3 ./flow worktree list --stale-only --json
```

3. Preview cleanup before mutating git:

```bash
python3 ./flow worktree clean --stale --dry-run --json
```

4. Execute cleanup once the preview is acceptable:

```bash
python3 ./flow worktree clean --stale --json
```

## Targeted cleanup

- Clean worktrees for a single feature:

```bash
python3 ./flow worktree clean --feature <slug> --dry-run --json
python3 ./flow worktree clean --feature <slug> --json
```

- Clean one explicit worktree by directory name:

```bash
python3 ./flow worktree clean <name> --dry-run --json
python3 ./flow worktree clean <name> --json
```

## Safety rules

- Do not remove dirty worktrees unless the operator explicitly asks for `--force`.
- Do not remove active plan worktrees unless the operator explicitly asks for `--force`.
- Prefer `--stale` when the goal is post-execution hygiene.
- Treat `.worktrees/**` as temporary operational state; the canonical source of truth remains the spec, the plan, and git history.

## Closeout checklist

- Feature/spec state reviewed in `.flow/state`
- Branch/worktree ownership confirmed
- `flow worktree clean` executed or deferred with reason
- CI/release evidence preserved before destructive cleanup
