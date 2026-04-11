---
schema_version: 3
name: "SoftOS Engram bootstrap and MCP template"
description: "Asegurar que workspaces generados hereden Engram con proyecto aislado, sin copiar DB local, y con una plantilla MCP opcional no activa por defecto."
status: approved
owner: platform
single_slice_reason: "bootstrap rewrite, MCP example, docs and tests are one bounded portability slice"
multi_domain: false
phases: []
depends_on:
  - specs/000-foundation/spec-as-source-operating-model.spec.md
  - specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - specs/features/softos-agent-memory-with-engram.spec.md
  - specs/features/softos-engram-devcontainer-install-and-smoke.spec.md
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
  - ../../scripts/bootstrap_workspace.py
  - ../../flowctl/test_bootstrap_workspace.py
  - ../../workspace.config.json
  - ../../.mcp.example.json
  - ../../README.md
  - ../../docs/softos-agent-dev-handbook.md
  - ../../specs/features/softos-engram-bootstrap-and-mcp-template.spec.md
---

# SoftOS Engram bootstrap and MCP template

## Objetivo

Completar la portabilidad de Engram para workspaces derivados:

- El bootstrap no copia bases de datos locales de `.flow/memory/**`.
- El bootstrap recrea solo `.flow/memory/.gitkeep`.
- `workspace.config.json` del nuevo workspace define `memory.agent.project=<root_repo>`.
- `.devcontainer/docker-compose.yml` del nuevo workspace usa `ENGRAM_PROJECT=<root_repo>` por defecto.
- Existe `.mcp.example.json` como plantilla opcional para agentes compatibles con MCP.

## Contexto

Engram ya esta instalado en el devcontainer y los wrappers `flow memory` ya funcionan. El riesgo
restante es que un workspace nuevo herede un proyecto de memoria incorrecto o copie una DB local del
boilerplate. Eso contaminaria memorias entre proyectos.

La solucion debe actuar en el bootstrap, porque ahi nace la identidad real del proyecto.

## Foundations Aplicables

- `spec-as-source-operating-model`
  la memoria sigue siendo consultiva y no fuente de verdad
- `spec-driven-delivery-and-infrastructure`
  bootstrap debe ser reproducible y verificable por tests
- `softos-engram-flow-memory-wrappers`
  los wrappers son la interfaz primaria; MCP es opcional

## Governing Decision

- La identidad de memoria por defecto del workspace derivado es `--root-repo`.
- `.flow/memory/**` nunca se copia desde el boilerplate al workspace nuevo.
- MCP no queda activo automaticamente; se entrega `.mcp.example.json` para opt-in explicito.
- La plantilla MCP usa `engram mcp` y el mismo `ENGRAM_DATA_DIR=/workspace/.flow/memory/engram`.

## Alcance

### Incluye

- rewrite de `workspace.config.json` con seccion `memory.agent`
- rewrite de `ENGRAM_PROJECT` en docker compose durante bootstrap
- `.mcp.example.json` versionado como ejemplo opt-in
- exclusion de `.flow/memory` al copiar template
- placeholder `.flow/memory/.gitkeep` en workspaces generados
- tests unitarios del bootstrap
- docs de MCP opcional y bootstrap multi-proyecto

### No incluye

- activar MCP automaticamente en clientes del usuario
- agregar secretos o tokens al MCP
- memoria global cross-project
- migracion/import/export de memorias entre workspaces
- Graphiti/Zep

## Slice Breakdown

```yaml
- name: engram-bootstrap-mcp-template
  targets:
    - ../../scripts/bootstrap_workspace.py
    - ../../flowctl/test_bootstrap_workspace.py
    - ../../workspace.config.json
    - ../../.mcp.example.json
    - ../../README.md
    - ../../docs/softos-agent-dev-handbook.md
    - ../../specs/features/softos-engram-bootstrap-and-mcp-template.spec.md
  hot_area: agent memory bootstrap portability
  depends_on: []
  slice_mode: minimal-change
  surface_policy: required
  minimum_valid_completion: new workspaces get isolated Engram identity and optional MCP example without copying DB state
  validated_noop_allowed: false
  acceptable_evidence:
    - python3 -m unittest flowctl.test_bootstrap_workspace
    - python3 ./flow ci spec specs/features/softos-engram-bootstrap-and-mcp-template.spec.md
```

## Verification Matrix

```yaml
- name: bootstrap-memory-unit
  level: custom
  command: python3 -m unittest flowctl.test_bootstrap_workspace
  blocking_on:
    - ci
  environments:
    - local
  notes: valida memory.agent.project, target roots, MCP example y placeholder de memoria

- name: spec-ci-bootstrap-memory
  level: custom
  command: python3 ./flow ci spec specs/features/softos-engram-bootstrap-and-mcp-template.spec.md
  blocking_on:
    - approval
  environments:
    - local
  notes: valida targets y estructura de la spec

- name: bootstrap-workspace-smoke
  level: smoke
  command: python3 scripts/bootstrap_workspace.py /tmp/softos-bootstrap-memory-smoke --project-name "Memory Smoke" --root-repo memory-smoke-root --profile master --force
  blocking_on:
    - ci
  environments:
    - local
  notes: valida que el workspace generado tenga proyecto de memoria aislado
```

## Acceptance Criteria

- `scripts/bootstrap_workspace.py` excluye `.flow/memory` al copiar el template.
- `reset_flow_state` crea `.flow/memory/.gitkeep`.
- El workspace generado tiene `workspace.config.json.memory.agent.project` igual a `--root-repo`.
- El compose generado usa `ENGRAM_PROJECT: ${ENGRAM_PROJECT:-<root_repo>}`.
- `.mcp.example.json` usa el root repo generado y `ENGRAM_DATA_DIR=/workspace/.flow/memory/engram`.
- Tests unitarios, spec CI y smoke de bootstrap pasan.
