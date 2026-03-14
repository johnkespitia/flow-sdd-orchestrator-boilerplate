---
name: Repo Routing And Worktree Orchestration
description: Reglas para enrutar specs centralizadas del root hacia submodulos y ejecutar slices por worktree
status: approved
owner: platform
targets:
  - ../../flow
  - ../../Makefile
  - ../../docs/spec-driven-orchestration.md
  - ../../AGENTS.md
---

# Repo Routing And Worktree Orchestration

## Objetivo

Definir como una spec del root decide en que repositorio se implementa cada slice y como se
materializa esa ejecucion usando worktrees.

## Regla de routing

- El routing se deduce desde `targets`.
- Si un target apunta a `../../backend/**`, la implementacion cae en `backend`.
- Si un target apunta a `../../frontend/**`, la implementacion cae en `frontend`.
- Si un target apunta a archivos del root, la implementacion cae en `workspace-root`.

## Regla de planning

- El orquestador vive en el root.
- El plan se guarda en `.flow/plans/**`.
- Cada slice pertenece a un solo repo.
- Cada slice tiene un branch y worktree dedicados.

## Regla de ownership

- Un slice no debe tocar targets fuera de su repo asignado.
- Si una feature afecta varios repos, el plan la separa en varias slices.
- Los hot files se congelan antes de paralelizar.

## Convenciones

### Branches

`feat/<feature>-<slice>`

### Worktrees

`<workspace-parent>/worktrees/<repo>-<feature>-<slice>`

## Verificacion

Antes de mergear una slice se debe revisar:

1. cumplimiento de la spec
2. tests relevantes
3. ausencia de drift entre spec, codigo y tests
