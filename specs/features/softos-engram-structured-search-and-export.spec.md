---
schema_version: 3
name: "SoftOS Engram structured search and export"
description: "Estructurar resultados de `flow memory search --json` y agregar `flow memory export` sobre `engram export` nativo para respaldos portables."
status: approved
owner: platform
single_slice_reason: "structured search parser and native export wrapper are one bounded memory portability slice"
multi_domain: false
phases: []
depends_on:
  - specs/000-foundation/spec-as-source-operating-model.spec.md
  - specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - specs/features/softos-engram-flow-memory-wrappers.spec.md
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
  - ../../specs/features/softos-engram-structured-search-and-export.spec.md
---

# SoftOS Engram structured search and export

## Objetivo

Convertir `flow memory search --json` en salida consumible por agentes y agregar export nativo:

- `flow memory search <query> --json` incluye `items[]` parseado.
- Se conserva `raw_stdout` y `step` para compatibilidad.
- `flow memory export --output <file>` usa `engram export` real.
- Si no se pasa `--output`, exporta a `.flow/memory/exports/<project>-<timestamp>.json`.

## Governing Decision

- `search` sigue usando la salida textual de Engram porque es el recall observado como confiable.
- El parser es tolerante y conserva `raw_stdout` para no perder informacion.
- `export` usa el formato JSON nativo de Engram, no un formato inventado por SoftOS.
- `.flow/memory/**` sigue ignorado por git.

## Slice Breakdown

```yaml
- name: structured-search-native-export
  targets:
    - ../../flow
    - ../../flowctl/parser.py
    - ../../flowctl/memory_ops.py
    - ../../flowctl/test_memory_ops.py
    - ../../README.md
    - ../../docs/softos-agent-dev-handbook.md
    - ../../specs/features/softos-engram-structured-search-and-export.spec.md
  hot_area: agent memory structured search export
  depends_on: []
  slice_mode: minimal-change
  surface_policy: required
  minimum_valid_completion: search JSON exposes parsed items and export wraps native Engram export
  validated_noop_allowed: false
  acceptable_evidence:
    - python3 -m unittest flowctl.test_memory_ops
    - python3 ./flow ci spec specs/features/softos-engram-structured-search-and-export.spec.md
    - scripts/workspace_exec.sh python3 ./flow memory export --json
```

## Verification Matrix

```yaml
- name: memory-structured-search-unit
  level: custom
  command: python3 -m unittest flowctl.test_memory_ops
  blocking_on:
    - ci
  environments:
    - local
  notes: valida parser de search y wrapper de export nativo

- name: spec-ci-structured-search-export
  level: custom
  command: python3 ./flow ci spec specs/features/softos-engram-structured-search-and-export.spec.md
  blocking_on:
    - approval
  environments:
    - local
  notes: valida targets y estructura

- name: memory-export-devcontainer
  level: smoke
  command: scripts/workspace_exec.sh python3 ./flow memory export --json
  blocking_on:
    - ci
  environments:
    - devcontainer
  notes: valida export nativo de Engram contra la DB aislada
```

## Acceptance Criteria

- `flow memory search --json` contiene `items` y `count`.
- Cada item parseado contiene `id`, `title`, `body`, `created_at`, `scope` y `kind`.
- `flow memory export --json` escribe un archivo JSON usando `engram export`.
- Tests unitarios, spec CI y smoke devcontainer pasan.
