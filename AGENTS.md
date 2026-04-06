# AGENTS.md

## Scope

This is a multi-project workspace. Use the nearest `AGENTS.md` plus parent `AGENTS.md` files to determine behavior.

## Project routing

- Use `backend/AGENTS.md` for backend specs, backend architecture, Tessl workflow, or files under `backend/**`.
- Use `frontend/AGENTS.md` for frontend specs, design-system work, routing migration, or files under `frontend/**`.
- Use root `specs/**` as the canonical source of truth for system-level features, cross-repo behavior, and orchestration rules.

## Skills por runtime

Cada proyecto tiene un runtime asociado (ej. `go-api`, `php`, `pnpm`). Los skills que aplican al proyecto se derivan del runtime:

1. **Resuelve el repo desde los targets de la spec**: `../../<repo>/**` → repo `<repo>`.
2. **Obtén runtime y skills del repo**: `workspace.config.json` → `repos[<repo>].runtime` y `repos[<repo>].agent_skill_refs`.
3. Si el repo no tiene `agent_skill_refs`, usa el runtime del repo: `runtimes/<runtime>.runtime.json` → `agent_skill_refs`.
4. **Carga y aplica esos skills** antes de implementar. La spec del root es la fuente de verdad; los skills complementan el contexto técnico.
5. `flow skills context --json` devuelve `agent_skills` con `path` para cada skill (`.tessl/tiles/...` o `.agents/skills/...`).

Comando rápido para obtener contexto:

```bash
python3 ./flow skills context --repo <repo> --json
```

Para descubrir o instalar skills nuevos:

```bash
python3 ./flow skills discover <query> [--limit 10] [--json]
python3 ./flow skills list --json
python3 ./flow skills install <identifier> --provider <tessl|skills-sh> --runtime <runtime>
```

Usa el skill `workspace/skills-discover` cuando necesites buscar skills en tessl.io o skills.sh.

## Default repo behavior

- Prefer spec-driven development for product or architecture changes.
- Do not assume backend rules apply to frontend tasks or vice versa.
- When a request is ambiguous between backend and frontend, ask one short clarifying question.
- When a root spec includes `targets` that point into a submodule, read the root spec first and then descend into the corresponding submodule `AGENTS.md` before editing code.
- Treat `.flow/**` as operational state only. It helps with orchestration, but it never overrides `specs/**`.
- Run workspace-managed toolchains from the devcontainer by default. Use `python3 ./flow workspace exec -- <cmd>` or `scripts/workspace_exec.sh <cmd>` from host.
- Run repo runtime commands in the repo service, not in `workspace`. Use `python3 ./flow repo exec <repo> -- <cmd>` for PHPUnit, Composer, pnpm, pytest, Go test, etc.
- If the command validates a slice worktree, use `python3 ./flow repo exec <repo> --workdir <worktree> -- <cmd>` so module resolution, autoload, caches and relative paths come from the worktree under test.
- If a slice is governance, enforcement, minimal-change, or verification-only, do not infer missing expansion work. Follow the spec's `surface_policy`, `minimum_valid_completion`, `validated_noop_allowed`, and `acceptable_evidence`.
- If no mandatory surface expansion appears after a short review, close the slice with the declared minimum diff and evidence instead of staying in analysis.
- Any new feature spec in `specs/features/**` must explicitly consider foundations (`specs/000-foundation/**`) and domains (`specs/domains/**`) through `depends_on` or a justified exclusion in the body.
- Do not modify files outside active spec `targets` unless the spec is updated first.
- Do not mark work complete without relevant `flow ci` evidence.

## SoftOS operating playbooks

For any AI agent working in this workspace, the following local playbooks are the preferred source of operational guidance:

- `.agents/skills/softos-agent-playbook/SKILL.md`
- `.agents/skills/softos-spec-definition-playbook/SKILL.md`
- `.agents/skills/softos-reference-spec-hardening/SKILL.md`
- `.agents/skills/softos-repo-ci-delegation/SKILL.md`
- `.agents/skills/softos-stack-compose-federation/SKILL.md`
- `.agents/skills/softos-release-manager/SKILL.md`

Apply them when the task touches:

- spec definition, spec review, or spec hardening
- hardening de specs aprobadas hacia reference specs con mínima deriva semántica
- spec lifecycle, workflow execution, or release state
- repo CI delegated from `root-ci.yml`
- project-owned `docker-compose.yml` files integrated into the workspace stack
- semver/changelog/GitHub Release publication

## Cross-agent compatibility

If the coding assistant supports only Markdown policy files instead of `.agents/skills/**`, use:

- `AGENTS.md` as the primary root contract
- `CURSOR.md` for Cursor CLI fallback context
- `OPENCODE.md` for OpenCode-style Markdown context loading
- `.cursor/rules/softos.mdc` for Cursor native rules
- `.cursor/rules/softos-enforcement.mdc` for blocking SoftOS guardrails

All three should be kept aligned with the playbooks above.
