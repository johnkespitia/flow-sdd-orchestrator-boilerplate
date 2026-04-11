---
schema_version: 3
name: "SoftOS Engram optional CI smoke"
description: "Agregar un workflow manual de GitHub Actions para validar `flow memory doctor` y `flow memory smoke` dentro del devcontainer sin convertir Engram en gate obligatorio de root CI."
status: approved
owner: platform
single_slice_reason: "manual CI smoke for agent memory is one bounded workflow slice"
multi_domain: false
phases: []
depends_on:
  - specs/000-foundation/spec-as-source-operating-model.spec.md
  - specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - specs/features/softos-engram-prune-retention-advisory.spec.md
required_runtimes: []
required_services: []
required_capabilities:
  - agent-memory-engram
stack_projects: []
stack_services: []
stack_capabilities:
  - agent-memory-engram
targets:
  - ../../.github/workflows/memory-smoke.yml
  - ../../flowctl/test_memory_ci_workflow.py
  - ../../README.md
  - ../../docs/softos-agent-dev-handbook.md
  - ../../specs/features/softos-engram-optional-ci-smoke.spec.md
---

# SoftOS Engram optional CI smoke

## Objetivo

Agregar una verificacion opcional de memoria en CI:

- Workflow `Agent Memory Smoke`.
- Trigger unico `workflow_dispatch`.
- Build y start del servicio `workspace` del devcontainer.
- Ejecucion de `flow memory doctor --json` y `flow memory smoke --json` dentro del devcontainer.
- Upload best-effort de `.flow/memory/` como artifact operativo.

## Governing Decision

- No se modifica `root-ci.yml`.
- Engram no se vuelve gate obligatorio para PRs ni pushes.
- El workflow existe para diagnostico manual de imagen/devcontainer y memoria aislada.
- La memoria sigue siendo consultiva; el smoke no reemplaza specs ni CI de features.

## Slice Breakdown

```yaml
- name: optional-memory-ci-smoke
  targets:
    - ../../.github/workflows/memory-smoke.yml
    - ../../flowctl/test_memory_ci_workflow.py
    - ../../README.md
    - ../../docs/softos-agent-dev-handbook.md
    - ../../specs/features/softos-engram-optional-ci-smoke.spec.md
  hot_area: agent memory ci smoke
  depends_on: []
  slice_mode: minimal-change
  surface_policy: required
  minimum_valid_completion: manual workflow exists and remains workflow_dispatch-only
  validated_noop_allowed: false
  acceptable_evidence:
    - python3 -m unittest flowctl.test_memory_ci_workflow
    - python3 ./flow ci spec specs/features/softos-engram-optional-ci-smoke.spec.md
```

## Verification Matrix

```yaml
- name: memory-ci-workflow-unit
  level: custom
  command: python3 -m unittest flowctl.test_memory_ci_workflow
  blocking_on:
    - ci
  environments:
    - local
  notes: valida que el workflow sea manual-only y use devcontainer workspace

- name: spec-ci-optional-memory-smoke
  level: custom
  command: python3 ./flow ci spec specs/features/softos-engram-optional-ci-smoke.spec.md
  blocking_on:
    - approval
  environments:
    - local
  notes: valida targets y estructura
```

## Acceptance Criteria

- Existe `.github/workflows/memory-smoke.yml`.
- El workflow solo usa `workflow_dispatch`.
- El workflow ejecuta doctor y smoke dentro del devcontainer `workspace`.
- `root-ci.yml` no queda acoplado a Engram.
- Tests unitarios y spec CI pasan.
