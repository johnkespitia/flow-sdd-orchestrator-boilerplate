---
schema_version: 3
name: "SoftOS Engram flow memory wrappers"
description: "Agregar wrappers `flow memory stats/search/save` y endurecer el smoke para validar `engram search`, manteniendo Engram como memoria consultiva y aislada por workspace."
status: approved
owner: platform
single_slice_reason: "CLI wrappers, tests and docs are one bounded memory ergonomics slice"
multi_domain: false
phases: []
depends_on:
  - specs/000-foundation/spec-as-source-operating-model.spec.md
  - specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - specs/features/softos-agent-memory-with-engram.spec.md
  - specs/features/softos-engram-devcontainer-install-and-smoke.spec.md
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
  - ../../.agents/skills/softos-agent-memory-playbook/SKILL.md
  - ../../docs/softos-agent-dev-handbook.md
  - ../../README.md
  - ../../specs/features/softos-engram-flow-memory-wrappers.spec.md
---

# SoftOS Engram flow memory wrappers

## Objetivo

Cerrar la segunda ola de ergonomia de memoria de agentes:

- `flow memory stats` para inspeccionar la DB del workspace.
- `flow memory search <query>` para recuperar memorias sin llamar Engram directo.
- `flow memory save <title> --body|--body-file` para guardar memorias explicitas.
- `flow memory smoke` valida tambien `engram search`, porque `search` es el camino que recupera
  memorias guardadas de forma confiable.

## Contexto

La ola anterior dejo Engram instalado automaticamente en el devcontainer y aislado en
`/workspace/.flow/memory/engram`.

La verificacion real mostro:

- `engram version` funciona.
- `engram stats` ve sesiones y observaciones.
- `engram search SoftOS` recupera memorias guardadas.
- `engram context softos-sdd-orchestrator` puede devolver vacio aunque existan memorias.

Por eso el flujo operativo principal debe usar `search` para recall, no depender de `context`.

## Foundations Aplicables

- `spec-as-source-operating-model`
  los wrappers no cambian la fuente autoritativa; memoria sigue siendo consultiva
- `spec-driven-delivery-and-infrastructure`
  el comportamiento debe tener tests y comandos reproducibles
- `softos-engram-devcontainer-install-and-smoke`
  reutiliza la instalacion y aislamiento ya publicados

## Governing Decision

- Los wrappers llaman la CLI real de Engram.
- `flow memory save` requiere input explicito; no guarda logs automaticamente.
- `flow memory search` es el camino recomendado para recall.
- `flow memory context` no se agrega todavia porque el comando observado no recupera memorias del
  proyecto de forma confiable.
- Si falta Engram, `doctor` sigue no bloqueante y los wrappers explicitos fallan con mensaje claro.

## Alcance

### Incluye

- `flow memory stats [--json]`
- `flow memory search <query> [--json]`
- `flow memory save <title> --body <text> [--json]`
- `flow memory save <title> --body-file <path> [--json]`
- smoke con `engram search <project>`
- unit tests de wrappers
- docs y playbook actualizados

### No incluye

- MCP auto-registration
- ingestion automatica de comandos/logs
- memoria global cross-project
- Graphiti/Zep
- comando `flow memory context`
- parsing semantico del output textual de Engram

## Execution Surface Inventory

### Write paths obligatorios

- `flow`
- `flowctl/parser.py`
- `flowctl/memory_ops.py`
- `flowctl/test_memory_ops.py`
- `.agents/skills/softos-agent-memory-playbook/SKILL.md`
- `README.md`
- `docs/softos-agent-dev-handbook.md`
- `specs/features/softos-engram-flow-memory-wrappers.spec.md`

### Read paths obligatorios

- `AGENTS.md`
- `.agents/skills/softos-agent-playbook/SKILL.md`
- `.agents/skills/softos-agent-memory-playbook/SKILL.md`
- `workspace.config.json`

## Slice Breakdown

```yaml
- name: flow-memory-wrapper-cli
  targets:
    - ../../flow
    - ../../flowctl/parser.py
    - ../../flowctl/memory_ops.py
    - ../../flowctl/test_memory_ops.py
    - ../../.agents/skills/softos-agent-memory-playbook/SKILL.md
    - ../../docs/softos-agent-dev-handbook.md
    - ../../README.md
    - ../../specs/features/softos-engram-flow-memory-wrappers.spec.md
  hot_area: agent memory wrappers
  depends_on: []
  slice_mode: minimal-change
  surface_policy: required
  minimum_valid_completion: flow memory exposes stats, search and save wrappers with smoke search validation
  validated_noop_allowed: false
  acceptable_evidence:
    - python3 -m unittest flowctl.test_memory_ops
    - python3 ./flow ci spec specs/features/softos-engram-flow-memory-wrappers.spec.md
    - scripts/workspace_exec.sh python3 ./flow memory search SoftOS --json
```

## Verification Matrix

```yaml
- name: memory-wrapper-unit
  level: custom
  command: python3 -m unittest flowctl.test_memory_ops
  blocking_on:
    - ci
  environments:
    - local
  notes: valida smoke con search y wrappers stats/search/save

- name: spec-ci-memory-wrappers
  level: custom
  command: python3 ./flow ci spec specs/features/softos-engram-flow-memory-wrappers.spec.md
  blocking_on:
    - approval
  environments:
    - local
  notes: valida estructura, targets y verification matrix

- name: memory-search-devcontainer
  level: smoke
  command: scripts/workspace_exec.sh python3 ./flow memory search SoftOS --json
  blocking_on:
    - ci
  environments:
    - devcontainer
  notes: valida recall real usando la DB aislada de Engram

- name: memory-save-devcontainer
  level: smoke
  command: 'scripts/workspace_exec.sh python3 ./flow memory save "SoftOS wrapper smoke" --body "TYPE outcome; Project softos-sdd-orchestrator; Area memory-wrapper-smoke; What flow memory save wrapper works; Evidence flow memory save --body" --json'
  blocking_on:
    - ci
  environments:
    - devcontainer
  notes: valida escritura explicita por wrapper
```

## Acceptance Criteria

- `flow memory smoke --json` incluye un paso `engram search <project>`.
- `flow memory stats --json` retorna salida estructurada con stdout/stderr del comando Engram.
- `flow memory search SoftOS --json` recupera memoria usando el storage del workspace.
- `flow memory save <title> --body ... --json` guarda memoria explicitamente.
- Los wrappers fallan con mensaje claro si Engram no esta disponible.
- Tests unitarios, spec CI y smoke devcontainer pasan.
