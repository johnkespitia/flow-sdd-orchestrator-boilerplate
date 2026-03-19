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
