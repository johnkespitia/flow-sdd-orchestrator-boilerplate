---
name: softos-release-manager
description: Use when publishing releases in a SoftOS workspace. Covers operational spec releases (`cut/promote/verify`) and OSS repo releases (`publish`) with semver, changelog, tags, and GitHub Release notes.
---

# SoftOS Release Manager

Use this skill when the task is to prepare, verify, promote, or publish a release in SoftOS.

## Two release layers

### 1. Operational feature release

Use this for approved feature specs that move through the SDLC:

```bash
python3 ./flow release cut --version <release-id> --spec <slug>
python3 ./flow release promote --version <release-id> --env <preview|staging|production>
python3 ./flow release verify --version <release-id> --env <preview|staging|production> --json
```

Rules:

- `cut` requires approved, executable specs
- `promote --env production` plus successful verification marks the feature `released`
- promoted production releases sync `.flow/state` and spec frontmatter to `status: released`

### 2. OSS repo release

Use this for versioned releases of the SoftOS repo itself:

```bash
python3 ./flow release publish --dry-run --skip-github --json
python3 ./flow release publish --bump auto
```

This flow:

- infers semver from conventional commits
- updates `CHANGELOG.md`
- creates a changelog commit
- creates/pushes the git tag
- optionally publishes the GitHub Release

## Semver rules

`flow release publish --bump auto` uses:

- `feat` -> minor
- `fix` -> patch
- `!` or `BREAKING CHANGE` -> major

If the history is messy, prefer an explicit bump:

```bash
python3 ./flow release publish --bump patch
python3 ./flow release publish --version v0.2.1
```

## Required checks

Before operational release:

```bash
python3 ./flow ci spec --all --json
python3 ./flow ci repo --all --json
python3 ./flow ci integration --profile smoke:ci-clean --auto-up --json
```

Before OSS repo release:

```bash
python3 ./flow release publish --dry-run --skip-github --json
```

## Rules

- Do not manually edit tags or changelog as a separate process if `flow release publish` can do it.
- Do not mark a spec `released` by hand; let `release promote` drive the state transition.
- Treat `released` as terminal. Do not re-plan or re-execute those specs.
- Keep operational feature releases and OSS repo releases conceptually separate.

## Files and artifacts

- `CHANGELOG.md`
- `releases/manifests/*.json`
- `releases/promotions/*.json`
- `.flow/state/<slug>.json`
- `specs/features/*.spec.md`

## Useful checks

```bash
python3 -m pytest -q flowctl/test_release_publish.py flowctl/test_release_verify.py
python3 ./flow release status --version <release-id> --json
python3 ./flow workflow next-step <slug> --json
```
