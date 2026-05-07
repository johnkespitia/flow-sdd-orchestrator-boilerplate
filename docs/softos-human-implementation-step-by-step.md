# SoftOS Human Implementation Step-by-Step

Spanish mirror: [docs/es/softos-human-implementation-step-by-step.es.md](./es/softos-human-implementation-step-by-step.es.md)

Source: `docs/softos-human-implementation-step-by-step.md`  
Last updated: 2026-05-07

This guide explains how a human team can implement and operate SoftOS end-to-end.

## 1. Define scope and repos

1. Identify the root workspace repository that will host `flow`, specs, and orchestration.
2. Identify implementation repositories (backend, frontend, services).
3. Register target repositories in `workspace.config.json`.

## 2. Bootstrap workspace

1. Create workspace from the SoftOS boilerplate.
2. Open the project in the devcontainer.
3. Run `python3 ./flow init`.
4. Run `python3 ./flow doctor` and resolve blockers.

## 3. Configure runtime and skills

1. Verify repo runtime mappings in `workspace.config.json`.
2. Verify runtime packs in `runtimes/*.runtime.json`.
3. Load contextual skills per repo:
   - `python3 ./flow skills context --repo <repo> --json`

## 4. Establish source-of-truth specs

1. Create/curate foundation specs in `specs/000-foundation/**`.
2. Define domain specs in `specs/domains/**`.
3. Define feature specs in `specs/features/**` with explicit dependencies.
4. Ensure each feature includes clear `targets` and validation plan.

## 5. Plan and execute slices

1. Run planning from spec:
   - `python3 ./flow plan <spec-id>`
2. Create/execute slices with bounded write-set.
3. Keep evidence in reports and CI outputs.
4. Avoid touching surfaces outside declared targets.

## 6. Run CI gates

1. Spec governance and contracts:
   - `python3 ./flow ci spec --changed --base <base> --head <head>`
2. Drift and contract verification:
   - `python3 ./flow drift check --changed --base <base> --head <head> --json`
   - `python3 ./flow contract verify --changed --base <base> --head <head> --json`
3. Repo runtime CI where applicable.

## 7. Operate release lifecycle

1. Cut release when spec and CI evidence are complete.
2. Promote release with staging preflight checks.
3. Verify rollout and capture evidence.
4. Publish release notes and tags.

## 8. Governance and observability

1. Use decision logs for exceptions.
2. Keep quality gates and risk policy visible.
3. Keep docs and specs synchronized with behavior.
4. Audit operational reports retention.

## 9. Documentation and i18n

1. English is canonical for new operational docs.
2. Spanish mirror is required for user-facing/operational docs.
3. Keep EN/ES links at top of each pair.
4. Validate with CI i18n guard.

## 10. Human operating checklist

- Workspace boots cleanly in devcontainer.
- `flow doctor` is green or only non-blocking warnings.
- Spec graph is explicit and current.
- CI evidence is reproducible.
- Promote preflight is deterministic.
- Release publication is traceable.
- Docs and mirrors are updated.
