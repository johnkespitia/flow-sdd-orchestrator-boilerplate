---
schema_version: 3
name: "SoftOS Engram autonomous flow hooks"
description: "Agregar hooks opcionales y no bloqueantes para recall de memoria antes de `flow plan` y guardado de outcome despues de `flow release publish` exitoso."
status: approved
owner: platform
single_slice_reason: "explicit memory hooks for plan and release publish are one bounded autonomous flow integration slice"
multi_domain: false
phases: []
depends_on:
  - specs/000-foundation/spec-as-source-operating-model.spec.md
  - specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - specs/features/softos-engram-optional-ci-smoke.spec.md
required_runtimes: []
required_services: []
required_capabilities:
  - agent-memory-engram
stack_projects: []
stack_services: []
stack_capabilities:
  - agent-memory-engram
targets:
  - ../../flow
  - ../../flowctl/parser.py
  - ../../flowctl/memory_ops.py
  - ../../flowctl/test_memory_ops.py
  - ../../workspace.config.json
  - ../../README.md
  - ../../docs/softos-agent-dev-handbook.md
  - ../../specs/features/softos-engram-autonomous-flow-hooks.spec.md
---

# SoftOS Engram autonomous flow hooks

## Objetivo

Integrar memoria consultiva en el flujo autonomo sin hacerla implicita:

- `flow plan <spec> --memory-recall` corre `engram search <slug>` antes de planificar.
- El recall escribe `.flow/reports/memory/<slug>-plan-recall.json`.
- `flow release publish --memory-save-outcome` guarda un outcome solo despues de publish real exitoso.
- `workspace.config.json` declara ambos gates apagados por defecto.

## Governing Decision

- La memoria sigue siendo consultiva y no reemplaza specs, CI, reports ni releases.
- Los hooks no bloquean si Engram falta.
- El hook de release no corre en `--dry-run`.
- Los hooks no imprimen payload extra para no romper salidas JSON existentes.
- No se activa autonomia completa de slices; solo recall previo y outcome posterior con gate explicito.

## Slice Breakdown

```yaml
- name: autonomous-memory-hooks
  targets:
    - ../../flow
    - ../../flowctl/parser.py
    - ../../flowctl/memory_ops.py
    - ../../flowctl/test_memory_ops.py
    - ../../workspace.config.json
    - ../../README.md
    - ../../docs/softos-agent-dev-handbook.md
    - ../../specs/features/softos-engram-autonomous-flow-hooks.spec.md
  hot_area: agent memory autonomous hooks
  depends_on: []
  slice_mode: minimal-change
  surface_policy: required
  minimum_valid_completion: explicit hooks exist, are off by default, and have unit coverage
  validated_noop_allowed: false
  acceptable_evidence:
    - python3 -m unittest flowctl.test_memory_ops
    - python3 ./flow ci spec specs/features/softos-engram-autonomous-flow-hooks.spec.md
    - scripts/workspace_exec.sh python3 ./flow plan specs/features/softos-engram-autonomous-flow-hooks.spec.md --memory-recall
```

## Verification Matrix

```yaml
- name: memory-hooks-unit
  level: custom
  command: python3 -m unittest flowctl.test_memory_ops
  blocking_on:
    - ci
  environments:
    - local
  notes: valida gates off-by-default, recall report y save outcome

- name: spec-ci-autonomous-memory-hooks
  level: custom
  command: python3 ./flow ci spec specs/features/softos-engram-autonomous-flow-hooks.spec.md
  blocking_on:
    - approval
  environments:
    - local
  notes: valida targets y estructura

- name: plan-memory-recall-devcontainer
  level: smoke
  command: scripts/workspace_exec.sh python3 ./flow plan specs/features/softos-engram-autonomous-flow-hooks.spec.md --memory-recall
  blocking_on:
    - ci
  environments:
    - devcontainer
  notes: valida recall real sin activar ejecucion de slices
```

## Acceptance Criteria

- `workspace.config.json` contiene `memory.execution.recall_before_plan=false`.
- `workspace.config.json` contiene `memory.execution.save_after_release_publish=false`.
- `flow plan --memory-recall` escribe reporte consultivo en `.flow/reports/memory`.
- `flow release publish --memory-save-outcome` intenta guardar memoria solo despues de publish exitoso.
- Tests unitarios, spec CI y smoke devcontainer pasan.
