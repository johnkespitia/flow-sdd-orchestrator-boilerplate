# SoftOS Cursor CLI Context

Use this file when Cursor CLI does not load `.cursor/rules/**` automatically.

## Mandatory SoftOS guardrails

- Root `specs/**` is the source of truth.
- `.flow/**` is operational state only; never treat it as canonical intent.
- Read the active spec and `workspace.config.json` before non-trivial edits.
- Resolve repo/runtime from spec `targets` and workspace routing.
- Do not edit files outside the active spec `targets` unless the spec changes first.
- Prefer `python3 ./flow ...` commands for lifecycle actions over ad hoc shell flows.
- Treat `status: released` as terminal: valid for CI/traceability, not valid for re-planning or re-execution.

## Required lifecycle behavior

Before claiming completion, run the relevant gates:

- `python3 ./flow ci spec --all --json` or the relevant `flow ci spec <spec>`
- `python3 ./flow ci repo --all --json` when implementation behavior changed
- `python3 ./flow ci integration --profile smoke:ci-clean --auto-up --json` when stack or cross-repo behavior changed

## Explicit prohibitions

- Do not implement first and repair specs later.
- Do not duplicate CI logic when `root-ci.yml` already dispatches project CI.
- Do not duplicate compose services when the repo already owns a compose file.
- Do not use `.flow/state` or `.flow/reports` to justify product behavior over specs.
- Do not close work without spec/governance alignment.

## Files to load together

- `AGENTS.md`
- `.cursor/rules/softos.mdc`
- `.cursor/rules/softos-enforcement.mdc`
- `OPENCODE.md`

If there is any conflict, follow this order:

1. `AGENTS.md`
2. `CURSOR.md`
3. `.cursor/rules/softos-enforcement.mdc`
4. `.cursor/rules/softos.mdc`
5. `OPENCODE.md`
