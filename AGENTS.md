# AGENTS.md

## Scope

This is a multi-project workspace. Use the nearest `AGENTS.md` plus parent `AGENTS.md` files to determine behavior.

## Project routing

- Use `backend/AGENTS.md` for backend specs, backend architecture, Tessl workflow, or files under `backend/**`.
- Use `frontend/AGENTS.md` for frontend specs, design-system work, routing migration, or files under `frontend/**`.
- Use root `specs/**` as the canonical source of truth for system-level features, cross-repo behavior, and orchestration rules.

## Default repo behavior

- Prefer spec-driven development for product or architecture changes.
- Do not assume backend rules apply to frontend tasks or vice versa.
- When a request is ambiguous between backend and frontend, ask one short clarifying question.
- When a root spec includes `targets` that point into a submodule, read the root spec first and then descend into the corresponding submodule `AGENTS.md` before editing code.
- Treat `.flow/**` as operational state only. It helps with orchestration, but it never overrides `specs/**`.
