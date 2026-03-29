# SoftOS OpenCode Context

Use this file as the root operational contract when the assistant does not load `.agents/skills/**` directly.

## Core rules

- Root `specs/**` is the source of truth.
- `.flow/**` is operational state only.
- Treat `status: released` as terminal:
  - valid for CI and traceability
  - not valid for re-planning or re-execution
- Prefer `flow` commands for lifecycle actions:
  - `flow spec review|approve`
  - `flow plan`
  - `flow workflow next-step|execute-feature|run`
  - `flow ci spec|repo|integration`
  - `flow release cut|promote|verify|publish`
  - `flow stack plan|apply`

## CI delegation

- If a repo declares project-owned CI in `workspace.config.json`, SoftOS root CI dispatches it.
- Delegated child workflows must use `workflow_dispatch` only.
- Do not configure delegated child workflows with `push` or `pull_request`.

## Compose federation

- If a repo already has its own compose file, include it in the workspace stack.
- Do not duplicate that service in `.devcontainer/docker-compose.yml`.

## Release model

- Operational feature releases use `flow release cut|promote|verify`.
- OSS repo releases use `flow release publish`.
- Use `flow release publish --dry-run --skip-github --json` before publishing.

## Local playbooks

- `.agents/skills/softos-agent-playbook/SKILL.md`
- `.agents/skills/softos-repo-ci-delegation/SKILL.md`
- `.agents/skills/softos-stack-compose-federation/SKILL.md`
- `.agents/skills/softos-release-manager/SKILL.md`
