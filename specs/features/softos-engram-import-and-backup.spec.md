---
schema_version: 3
name: "SoftOS Engram import and backup"
description: "Agregar `flow memory backup` y `flow memory import` con dry-run por defecto, confirmacion explicita y validacion anti-secret antes de importar exports nativos de Engram."
status: approved
owner: platform
single_slice_reason: "backup and guarded import are one bounded memory portability slice"
multi_domain: false
phases: []
depends_on:
  - specs/000-foundation/spec-as-source-operating-model.spec.md
  - specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - specs/features/softos-engram-structured-search-and-export.spec.md
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
  - ../../specs/features/softos-engram-import-and-backup.spec.md
---

# SoftOS Engram import and backup

## Objetivo

Hacer portables las memorias Engram sin copiar `.flow/memory/engram.db`:

- `flow memory backup --json` crea un export nativo timestamped.
- `flow memory import <file> --json` valida el export sin importarlo.
- `flow memory import <file> --confirm --json` ejecuta `engram import`.
- El import bloquea contenido con patrones obvios de secrets.

## Governing Decision

- Import es dry-run por defecto.
- La ejecucion real requiere `--confirm`.
- No se importan archivos que contengan patrones tipo `token=`, `secret:`, `password=`,
  `api_key=` o `private_key=`.
- Backup usa el formato nativo de Engram.

## Slice Breakdown

```yaml
- name: native-backup-guarded-import
  targets:
    - ../../flow
    - ../../flowctl/parser.py
    - ../../flowctl/memory_ops.py
    - ../../flowctl/test_memory_ops.py
    - ../../README.md
    - ../../docs/softos-agent-dev-handbook.md
    - ../../specs/features/softos-engram-import-and-backup.spec.md
  hot_area: agent memory backup import
  depends_on: []
  slice_mode: minimal-change
  surface_policy: required
  minimum_valid_completion: backup writes native export and import is dry-run unless confirmed
  validated_noop_allowed: false
  acceptable_evidence:
    - python3 -m unittest flowctl.test_memory_ops
    - python3 ./flow ci spec specs/features/softos-engram-import-and-backup.spec.md
    - scripts/workspace_exec.sh python3 ./flow memory backup --json
```

## Verification Matrix

```yaml
- name: memory-import-backup-unit
  level: custom
  command: python3 -m unittest flowctl.test_memory_ops
  blocking_on:
    - ci
  environments:
    - local
  notes: valida backup, import dry-run, import confirm y bloqueo anti-secret

- name: spec-ci-import-backup
  level: custom
  command: python3 ./flow ci spec specs/features/softos-engram-import-and-backup.spec.md
  blocking_on:
    - approval
  environments:
    - local
  notes: valida targets y estructura

- name: memory-backup-devcontainer
  level: smoke
  command: scripts/workspace_exec.sh python3 ./flow memory backup --json
  blocking_on:
    - ci
  environments:
    - devcontainer
  notes: valida backup nativo contra la DB aislada
```

## Acceptance Criteria

- `flow memory backup --json` escribe en `.flow/memory/backups`.
- `flow memory import <file> --json` no ejecuta import real.
- `flow memory import <file> --confirm --json` ejecuta `engram import`.
- Import bloquea patrones de secretos antes de invocar Engram.
- Tests unitarios, spec CI y smoke devcontainer pasan.
