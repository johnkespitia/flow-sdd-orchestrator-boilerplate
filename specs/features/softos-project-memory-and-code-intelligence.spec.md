---
schema_version: 3
name: "SoftOS project memory and code intelligence"
description: "Actualizar Engram estable e integrar Graphify Labs como indice local de codigo por cada repo registrado, sin broker ni daemon."
status: approved
owner: platform
single_slice_reason: "Engram compatibility, Graphify lifecycle, MCP wiring and bootstrap form one bounded workspace context-primitives rollout."
multi_domain: false
phases: []
depends_on:
  - specs/000-foundation/spec-as-source-operating-model.spec.md
  - specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - specs/000-foundation/repo-routing-and-worktree-orchestration.spec.md
  - specs/features/softos-agent-memory-with-engram.spec.md
  - specs/features/softos-engram-devcontainer-install-and-smoke.spec.md
  - specs/features/softos-engram-client-mcp-activation.spec.md
required_runtimes: []
required_services: []
required_capabilities:
  - agent-memory-engram
  - agent-code-intelligence-graphify
stack_projects: []
stack_services: []
stack_capabilities:
  - agent-memory-engram
  - agent-code-intelligence-graphify
targets:
  - ../../.devcontainer/Dockerfile
  - ../../.devcontainer/workspace-entrypoint.sh
  - ../../.cursor/mcp.json
  - ../../.gitignore
  - ../../.mcp.example.json
  - ../../capabilities/agent-code-intelligence-graphify.capability.json
  - ../../docs/external-tooling-updates.md
  - ../../docs/es/external-tooling-updates.es.md
  - ../../docs/es/softos-agent-dev-handbook.es.md
  - ../../docs/softos-agent-dev-handbook.md
  - ../../flow
  - ../../flowctl/code_graph_ops.py
  - ../../flowctl/memory_ops.py
  - ../../flowctl/parser.py
  - ../../flowctl/test_agent_memory_capability.py
  - ../../flowctl/test_bootstrap_workspace.py
  - ../../flowctl/test_code_graph_ops.py
  - ../../flowctl/test_memory_ops.py
  - ../../flowctl/test_workspace_exec_user.py
  - ../../opencode.json
  - ../../README.md
  - ../../scripts/bootstrap_workspace.py
  - ../../scripts/install_codex_graphify_mcp.sh
  - ../../specs/features/softos-project-memory-and-code-intelligence.spec.md
  - ../../workspace.capabilities.json
  - ../../workspace.config.json
---

# SoftOS project memory and code intelligence

## Objetivo

Establecer dos primitivas independientes de contexto para agentes:

- Engram v1.20.0 como memoria persistente, consultiva y aislada por workspace.
- Graphify Labs v0.9.56 como representacion local y reconstruible del codigo actual, con un indice por repo registrado.

Git/codigo y `specs/**` permanecen autoritativos. Esta feature no crea un Context Broker.

## Contexto y hallazgos

Engram ya se instala en el devcontainer y usa `.flow/memory/engram`, pero la imagen resuelve
`latest` sin checksum y la documentacion conserva referencias a v1.11.0. La imagen materializada
contiene v1.20.0. El entrypoint baja a UID/GID de `vscode` pero conserva `HOME=/root`, lo que rompe
el contrato de tooling no-root.

Graphify no existe en SoftOS. La distribucion seleccionada es `Graphify-Labs/graphify`, paquete
PyPI `graphifyy`, v0.9.56. Soporta AST local, cache/manifest incremental y MCP stdio cuyas
herramientas aceptan un `project_path` opcional.

## Foundations Aplicables

- `spec-as-source-operating-model`: memoria e indices son consultivos/derivados.
- `spec-driven-delivery-and-infrastructure`: instalacion, CLI y smoke requieren evidencia.
- `repo-routing-and-worktree-orchestration`: los repos se descubren solo desde `workspace.config.json.repos`.

## Domains Aplicables

No aplica domain porque no se introduce una ontologia de producto ni un modelo de conocimiento
compartido; Graphify es un indice tecnico reconstruible.

## Alcance

### Incluye

- pin y verificacion de Engram v1.20.0 sin reemplazar su DB;
- correccion de `HOME`, `USER` y `LOGNAME` para el usuario efectivo `vscode`;
- diagnostico Engram de version, storage, identidad y escritura;
- instalacion local de `graphifyy[mcp]==0.9.56`;
- discovery exclusivo de repos registrados;
- un `graphify-out/` por repo y exclusion de repos hijos al indexar el root;
- lifecycle explicito `doctor`, `status` y `refresh`;
- Graphify code-only sin API keys ni uploads;
- MCP de proyecto para Cursor/OpenCode y activacion explicita para Codex;
- bootstrap, tests, docs y smoke.

### No incluye

- Context Broker, Graphiti, vector DB, embeddings, RAG o knowledge graph global;
- daemon, watch, hooks Git o indexacion automatica desde `flow add-project`;
- combinacion de varios repos en un mismo grafo;
- servicios cloud, HTTP MCP o subida de codigo;
- correcciones de pnpm/Node, Gateway o puertos no causadas por esta feature.

## Invariantes

- Engram nunca reemplaza specs, Git, CI ni evidencia.
- Graphify nunca almacena decisiones historicas como memoria SoftOS.
- Solo se indexan entradas de `workspace.config.json.repos`.
- Un error de repo no cancela el procesamiento de otros repos.
- Un lenguaje no soportado, repo vacio o submodulo ausente produce warning por repo.
- `flow add-project` registra; `flow code-graph refresh` indexa explicitamente.
- Procesos y archivos runtime quedan escribibles por `vscode`, sin `chmod 777` ni `chown` global.
- Engram conserva `.flow/memory/engram`; Graphify puede reconstruirse desde el codigo.

## Contrato de configuracion

`workspace.config.json.code_graph` declara:

- `provider: graphify`
- `version: 0.9.56`
- `output_dir: graphify-out`
- `mode: code-only`
- `source_boundary: derived`

La identidad de memoria permanece en `memory.agent.project`. No se mezcla con IDs de grafos.

## Contrato CLI

- `flow memory doctor [--json]`: disponibilidad, version, identidad, storage y escritura.
- `flow code-graph doctor [--json]`: binario/version, MCP y resumen de repos gestionados.
- `flow code-graph status [repo] [--json]`: lista determinista con estados
  `current|stale|missing|unsupported|error`.
- `flow code-graph refresh [repo|--all] [--json]`: crea o actualiza incrementalmente indices.

`status` no modifica indices. `refresh` retorna resultado parcial por repo y codigo distinto de cero
solo cuando existe un error operacional, no por unsupported/empty.

## Freshness V1

Un indice es:

- `missing` si falta `graphify-out/graph.json`;
- `unsupported` si no hay archivos con extensiones soportadas;
- `error` si el repo/config/manifest no puede inspeccionarse;
- `stale` si el registro/exclusiones cambiaron o una fuente es posterior al grafo;
- `current` en caso contrario.

Este check es determinista y deliberadamente simple; Graphify conserva su propio manifest/cache
para decidir el trabajo incremental real.

## MCP

- Cursor y OpenCode lanzan un Graphify MCP stdio para el grafo root del proyecto.
- Otros repos conservan grafos independientes; las herramientas MCP aceptan `project_path`, que
  los agentes SoftOS deben resolver exclusivamente desde repos registrados.
- El server puede iniciar sin grafo y reportar que primero debe ejecutarse `refresh`.
- Codex usa un instalador explicito porque su configuracion es global al usuario.
- No se inicia servidor persistente ni se expone puerto.

## Persistencia y migracion

- La DB Engram no se borra, mueve ni recrea; v1.20.0 abre el mismo `ENGRAM_DATA_DIR`.
- Se recomienda `flow memory backup` antes de upgrades, sin forzar una export destructiva.
- `graphify-out/` se ignora localmente y permanece en los bind mounts entre rebuilds.
- Bootstrap no copia memoria ni indices desde el boilerplate.
- El rollback restaura binarios/config; la memoria existente permanece y los indices se regeneran.

## Slice Breakdown

```yaml
- name: project-context-primitives
  targets:
    - ../../.devcontainer/Dockerfile
    - ../../.devcontainer/workspace-entrypoint.sh
    - ../../.cursor/mcp.json
    - ../../.gitignore
    - ../../.mcp.example.json
    - ../../capabilities/agent-code-intelligence-graphify.capability.json
    - ../../docs/external-tooling-updates.md
    - ../../docs/es/external-tooling-updates.es.md
    - ../../docs/es/softos-agent-dev-handbook.es.md
    - ../../docs/softos-agent-dev-handbook.md
    - ../../flow
    - ../../flowctl/code_graph_ops.py
    - ../../flowctl/memory_ops.py
    - ../../flowctl/parser.py
    - ../../flowctl/test_agent_memory_capability.py
    - ../../flowctl/test_bootstrap_workspace.py
    - ../../flowctl/test_code_graph_ops.py
    - ../../flowctl/test_memory_ops.py
    - ../../flowctl/test_workspace_exec_user.py
    - ../../opencode.json
    - ../../README.md
    - ../../scripts/bootstrap_workspace.py
    - ../../scripts/install_codex_graphify_mcp.sh
    - ../../workspace.capabilities.json
    - ../../workspace.config.json
  hot_area: workspace project context primitives
  depends_on: []
  slice_mode: implementation-heavy
  surface_policy: required
  minimum_valid_completion: Engram stable plus Graphify per-repo lifecycle, MCP, tests and live smoke
  validated_noop_allowed: false
  acceptable_evidence:
    - python3 -m unittest flowctl.test_memory_ops flowctl.test_code_graph_ops flowctl.test_bootstrap_workspace flowctl.test_agent_memory_capability
    - python3 -m pytest flowctl/test_workspace_exec_user.py
    - python3 ./flow ci spec specs/features/softos-project-memory-and-code-intelligence.spec.md
    - python3 ./flow code-graph status --json
```

## Verification Matrix

```yaml
- name: project-context-unit
  level: custom
  command: python3 -m unittest flowctl.test_memory_ops flowctl.test_code_graph_ops flowctl.test_bootstrap_workspace flowctl.test_agent_memory_capability
  blocking_on:
    - ci
  environments:
    - local
  notes: valida Engram, discovery, lifecycle, aislamiento y bootstrap sin red

- name: runtime-user-contract
  level: custom
  command: python3 -m pytest flowctl/test_workspace_exec_user.py
  blocking_on:
    - ci
  environments:
    - local
  notes: valida que el entrypoint materializa HOME y usuario no-root

- name: project-context-spec
  level: custom
  command: python3 ./flow ci spec specs/features/softos-project-memory-and-code-intelligence.spec.md
  blocking_on:
    - approval
  environments:
    - local
  notes: valida targets y contrato

- name: project-context-live
  level: smoke
  command: scripts/workspace_exec.sh python3 ./flow code-graph refresh sdd-workspace-boilerplate --json
  blocking_on:
    - ci
  environments:
    - devcontainer
  notes: valida Graphify local contra un repo representativo
```

## Criterios de aceptacion

- Engram v1.20.0 se instala con checksum y conserva el storage existente.
- `vscode` ejecuta con UID 1000 y `HOME=/home/vscode`.
- Engram puede escribir/leer memoria y exponer MCP.
- Graphify v0.9.56 se instala con extra MCP y sin cloud por defecto.
- Todos los repos registrados aparecen en status; cada repo tiene indice independiente.
- Refresh incremental, freshness minima y errores por repo tienen pruebas.
- MCP Graphify consulta al menos un grafo desde un executor compatible.
- No se agregan daemon, broker, vector DB ni uploads.
- Tests, spec CI y smoke live pasan o documentan un blocker externo verificable.
