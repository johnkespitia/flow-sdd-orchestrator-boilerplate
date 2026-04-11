---
schema_version: 3
name: "SoftOS Engram client MCP activation"
description: "Activar Engram MCP por cliente donde exista configuracion de proyecto, y proveer instalador explicito para Codex que usa configuracion de usuario."
status: approved
owner: platform
single_slice_reason: "client MCP config files, Codex installer, bootstrap rewrite and docs form one bounded activation slice"
multi_domain: false
phases: []
depends_on:
  - specs/000-foundation/spec-as-source-operating-model.spec.md
  - specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - specs/features/softos-agent-memory-with-engram.spec.md
  - specs/features/softos-engram-bootstrap-and-mcp-template.spec.md
required_runtimes: []
required_services: []
required_capabilities:
  - agent-memory-engram
stack_projects: []
stack_services: []
stack_capabilities:
  - agent-memory-engram
targets:
  - ../../.cursor/mcp.json
  - ../../opencode.json
  - ../../scripts/install_codex_engram_mcp.sh
  - ../../scripts/bootstrap_workspace.py
  - ../../flowctl/test_bootstrap_workspace.py
  - ../../workspace.config.json
  - ../../README.md
  - ../../docs/softos-agent-dev-handbook.md
  - ../../specs/features/softos-engram-client-mcp-activation.spec.md
---

# SoftOS Engram client MCP activation

## Objetivo

Activar Engram MCP por cliente sin mezclar memorias entre proyectos:

- Cursor usa `.cursor/mcp.json` versionado.
- OpenCode usa `opencode.json` versionado.
- Codex usa `scripts/install_codex_engram_mcp.sh` porque su configuracion MCP real vive en el usuario.
- Bootstrap reescribe esos archivos con el `--root-repo` del workspace nuevo.

## Contexto

La ola anterior dejo `.mcp.example.json`, pero eso era una plantilla generica. Para que el uso sea
real por cliente hay que declarar los formatos que cada cliente carga:

- Cursor carga `.cursor/mcp.json` por proyecto.
- OpenCode carga MCP desde `opencode.json`.
- Codex administra servidores MCP con `codex mcp add`, que modifica configuracion de usuario.

## Governing Decision

- No se escriben archivos globales del usuario desde el bootstrap.
- Cursor/OpenCode quedan activos a nivel de proyecto.
- Codex requiere ejecucion explicita del instalador porque toca configuracion de usuario.
- Todas las configuraciones apuntan a `engram mcp` y al storage aislado `/workspace/.flow/memory/engram`.

## Slice Breakdown

```yaml
- name: client-mcp-activation
  targets:
    - ../../.cursor/mcp.json
    - ../../opencode.json
    - ../../scripts/install_codex_engram_mcp.sh
    - ../../scripts/bootstrap_workspace.py
    - ../../flowctl/test_bootstrap_workspace.py
    - ../../workspace.config.json
    - ../../README.md
    - ../../docs/softos-agent-dev-handbook.md
    - ../../specs/features/softos-engram-client-mcp-activation.spec.md
  hot_area: agent memory MCP client activation
  depends_on: []
  slice_mode: minimal-change
  surface_policy: required
  minimum_valid_completion: Cursor and OpenCode have project MCP configs; Codex has explicit installer
  validated_noop_allowed: false
  acceptable_evidence:
    - python3 -m unittest flowctl.test_bootstrap_workspace
    - python3 ./flow ci spec specs/features/softos-engram-client-mcp-activation.spec.md
    - scripts/workspace_exec.sh engram mcp --help
```

## Verification Matrix

```yaml
- name: bootstrap-mcp-client-unit
  level: custom
  command: python3 -m unittest flowctl.test_bootstrap_workspace
  blocking_on:
    - ci
  environments:
    - local
  notes: valida rewrite de Cursor/OpenCode/MCP example por root_repo

- name: spec-ci-client-mcp
  level: custom
  command: python3 ./flow ci spec specs/features/softos-engram-client-mcp-activation.spec.md
  blocking_on:
    - approval
  environments:
    - local
  notes: valida targets y matriz

- name: engram-mcp-help
  level: smoke
  command: scripts/workspace_exec.sh engram mcp --help
  blocking_on:
    - ci
  environments:
    - devcontainer
  notes: valida que el binario expone el modo MCP
```

## Acceptance Criteria

- `.cursor/mcp.json` declara el server `engram`.
- `opencode.json` declara MCP local `engram` habilitado.
- `scripts/install_codex_engram_mcp.sh` instala un server MCP Codex usando `codex mcp add`.
- Bootstrap reescribe Cursor/OpenCode/MCP example al `--root-repo` nuevo.
- Tests unitarios, spec CI y smoke de `engram mcp` pasan.
