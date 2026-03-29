---
name: softos-repo-ci-delegation
description: Use when a project repo should keep its own GitHub Actions CI pipeline but SoftOS root CI must be the only trigger. Covers workspace.config.json metadata, root-ci dispatch, and child workflow constraints.
---

# SoftOS Repo CI Delegation

Use this skill when a repo has its own CI workflow and SoftOS root CI must dispatch it.

## Goal

Let the project keep its pipeline logic without duplicating it in `root-ci.yml`, while ensuring:

- the child workflow does not run on `push`
- the child workflow does not run on `pull_request`
- SoftOS root CI is the single orchestrator

## Required repo contract

In `workspace.config.json`, declare:

```json
"ci": {
  "mode": "workflow-dispatch",
  "workflow": "repo-ci.yml",
  "trigger_mode": "workflow_dispatch_only"
}
```

Optional:

```json
"ci": {
  "mode": "workflow-dispatch",
  "workflow": "repo-ci.yml",
  "workflow_repository": "owner/project-repo",
  "trigger_mode": "workflow_dispatch_only",
  "inputs": {
    "repo": "my-repo",
    "repo_path": "projects/my-repo"
  }
}
```

## Child workflow rules

Allowed:

```yaml
on:
  workflow_dispatch:
```

Optionally:

```yaml
on:
  workflow_dispatch:
    inputs: ...
```

Forbidden for delegated child workflows:

- `on: push`
- `on: pull_request`

Reason: the project workflow must only run when SoftOS root dispatches it.

## Root CI behavior

- `root-ci.yml` discovers repo entries from `workspace.config.json`
- if `ci.mode=workflow-dispatch`, it dispatches the child workflow and waits
- if not declared, it falls back to generic `flow ci repo <repo>`

## Validation checklist

1. Child workflow has only `workflow_dispatch`.
2. Root metadata points to the correct workflow name/repo.
3. Root CI blocks integration until delegated workflows pass.
4. There is no duplicate CI execution on `push`.

## Files to touch

- `.github/workflows/root-ci.yml`
- `workspace.config.json`
- project `.github/workflows/<repo-ci>.yml`
- `scripts/ci/discover_repo_ci_matrix.py`
- `scripts/ci/run_project_workflow.sh`

## Useful checks

```bash
python3 ./scripts/ci/discover_repo_ci_matrix.py
python3 -m pytest -q flowctl/test_repo_ci_matrix.py
```
