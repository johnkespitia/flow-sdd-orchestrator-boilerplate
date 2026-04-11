---
schema_version: 3
name: "SoftOS Engram prune retention advisory"
description: "Agregar `flow memory prune` como reporte no destructivo de candidatos de limpieza para memoria Engram, basado en query, edad, retention y duplicados."
status: approved
owner: platform
single_slice_reason: "prune advisory is one bounded memory retention slice"
multi_domain: false
phases: []
depends_on:
  - specs/000-foundation/spec-as-source-operating-model.spec.md
  - specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - specs/features/softos-engram-import-and-backup.spec.md
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
  - ../../README.md
  - ../../docs/softos-agent-dev-handbook.md
  - ../../specs/features/softos-engram-prune-retention-advisory.spec.md
---

# SoftOS Engram prune retention advisory

## Objetivo

Agregar una limpieza segura de memoria en modo advisory:

- `flow memory prune --query <text> --json` genera candidatos por texto.
- `flow memory prune --older-than-days <n> --json` genera candidatos por antiguedad.
- `flow memory prune --keep-latest <n> --json` genera candidatos fuera de retention.
- El reporte tambien marca duplicados por fingerprint o `duplicate_count`.
- La operacion no borra memorias porque Engram v1.11.0 no expone delete granular seguro.

## Governing Decision

- `prune` es explicitamente no destructivo.
- La fuente del reporte es un `engram export` nativo timestamped.
- El reporte queda en `.flow/memory/prune` salvo que se pase `--output`.
- La decision humana/agente posterior debe usar el reporte como evidencia consultiva, no como mutacion automatica.

## Slice Breakdown

```yaml
- name: prune-retention-advisory
  targets:
    - ../../flow
    - ../../flowctl/parser.py
    - ../../flowctl/memory_ops.py
    - ../../flowctl/test_memory_ops.py
    - ../../README.md
    - ../../docs/softos-agent-dev-handbook.md
    - ../../specs/features/softos-engram-prune-retention-advisory.spec.md
  hot_area: agent memory prune retention
  depends_on: []
  slice_mode: minimal-change
  surface_policy: required
  minimum_valid_completion: prune creates a non-destructive advisory report from native Engram export
  validated_noop_allowed: false
  acceptable_evidence:
    - python3 -m unittest flowctl.test_memory_ops
    - python3 ./flow ci spec specs/features/softos-engram-prune-retention-advisory.spec.md
    - scripts/workspace_exec.sh python3 ./flow memory prune --query smoke --keep-latest 200 --json
```

## Verification Matrix

```yaml
- name: memory-prune-unit
  level: custom
  command: python3 -m unittest flowctl.test_memory_ops
  blocking_on:
    - ci
  environments:
    - local
  notes: valida reporte advisory no destructivo

- name: spec-ci-prune-retention
  level: custom
  command: python3 ./flow ci spec specs/features/softos-engram-prune-retention-advisory.spec.md
  blocking_on:
    - approval
  environments:
    - local
  notes: valida targets y estructura

- name: memory-prune-devcontainer
  level: smoke
  command: scripts/workspace_exec.sh python3 ./flow memory prune --query smoke --keep-latest 200 --json
  blocking_on:
    - ci
  environments:
    - devcontainer
  notes: valida reporte no destructivo contra la DB aislada
```

## Acceptance Criteria

- `flow memory prune --json` genera un reporte con `mode: advisory`.
- El reporte contiene `destructive: false`.
- Los candidatos incluyen razones como `query`, `older_than_days`, `beyond_keep_latest` o `duplicate`.
- El comando no invoca deletes ni modifica memoria Engram.
- Tests unitarios, spec CI y smoke devcontainer pasan.
