---
schema_version: 3
name: "SoftOS Engram devcontainer install and smoke"
description: "Instalar Engram automaticamente en el devcontainer, aislar su memoria por workspace y exponer comandos `flow memory` para doctor/smoke sin convertir memoria en gate obligatorio del SDLC."
status: approved
owner: platform
single_slice_reason: "devcontainer install, CLI smoke and docs form one bounded bootstrap slice"
multi_domain: false
phases: []
depends_on:
  - specs/000-foundation/spec-as-source-operating-model.spec.md
  - specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - specs/features/softos-agent-memory-with-engram.spec.md
required_runtimes: []
required_services: []
required_capabilities:
  - agent-memory-engram
stack_projects: []
stack_services: []
stack_capabilities:
  - agent-memory-engram
targets:
  - ../../.devcontainer/Dockerfile
  - ../../.devcontainer/docker-compose.yml
  - ../../.gitignore
  - ../../.flow/memory/.gitkeep
  - ../../flow
  - ../../workspace.config.json
  - ../../flowctl/parser.py
  - ../../flowctl/memory_ops.py
  - ../../flowctl/test_memory_ops.py
  - ../../flowctl/test_agent_memory_capability.py
  - ../../capabilities/agent-memory-engram.capability.json
  - ../../.agents/skills/softos-agent-memory-playbook/SKILL.md
  - ../../docs/softos-agent-dev-handbook.md
  - ../../README.md
  - ../../specs/features/softos-engram-devcontainer-install-and-smoke.spec.md
---

# SoftOS Engram devcontainer install and smoke

## Objetivo

Convertir la capability `agent-memory-engram` de documentacion/playbook a integracion operable:

- Engram queda instalado automaticamente al construir el devcontainer.
- La memoria queda aislada por proyecto bajo `.flow/memory/engram`.
- `flow memory doctor` muestra disponibilidad, proyecto y ubicacion de storage.
- `flow memory smoke` valida el binario y storage sin volver memoria un gate obligatorio.

## Contexto

La ola anterior dejo una frontera segura:

- memoria consultiva, nunca autoritativa
- ausencia de Engram no bloquea SDLC
- no se guardan secretos ni outputs brutos
- specs, reports, CI y releases siguen siendo fuente de verdad

El siguiente problema practico es instalacion y reproducibilidad. Si cada agente instala Engram a mano
en el host, aparecen dos fallos:

- contaminacion entre proyectos por una base de datos global
- setups no reproducibles entre devcontainers y maquinas

Por eso esta ola instala Engram dentro del devcontainer y fija `ENGRAM_DATA_DIR` al workspace.

## Foundations Aplicables

- `spec-as-source-operating-model`
  memoria no reemplaza specs, AGENTS ni reports
- `spec-driven-delivery-and-infrastructure`
  instalacion debe ser verificable por comandos y no por narrativa
- `softos-agent-memory-with-engram`
  Engram sigue siendo opcional y consultivo

## Governing Decision

- Engram se instala en la imagen `workspace`, no globalmente en el host.
- El storage por defecto es `/workspace/.flow/memory/engram`.
- `.flow/memory/**` no se versiona.
- `flow memory doctor` nunca debe fallar solo porque Engram falte.
- `flow memory smoke` puede fallar si Engram falta, porque es un smoke explicito de instalacion.
- El smoke solo valida memoria; no habilita ejecucion autonoma de slices ni release.

## Alcance

### Incluye

- instalacion automatica de Engram desde GitHub Releases durante build del devcontainer
- variables `ENGRAM_PROJECT` y `ENGRAM_DATA_DIR` en el servicio `workspace`
- comando `flow memory doctor`
- comando `flow memory smoke`
- opcion `flow memory smoke --save` para escribir una memoria estructurada de prueba
- tests unitarios para configuracion, comportamiento no bloqueante y comando smoke
- docs y playbook actualizados

### No incluye

- instalacion global en host
- sync de `.flow/memory/**` al repo
- Git sync de Engram
- MCP auto-registrado en todos los agentes
- Graphiti/Zep
- memoria como gate de `flow ci`, `flow plan`, `flow release` o specs

## Execution Surface Inventory

### Write paths obligatorios

- `.devcontainer/Dockerfile`
- `.devcontainer/docker-compose.yml`
- `.gitignore`
- `.flow/memory/.gitkeep`
- `flow`
- `workspace.config.json`
- `flowctl/parser.py`
- `flowctl/memory_ops.py`
- `flowctl/test_memory_ops.py`
- `flowctl/test_agent_memory_capability.py`
- `capabilities/agent-memory-engram.capability.json`
- `.agents/skills/softos-agent-memory-playbook/SKILL.md`
- `README.md`
- `docs/softos-agent-dev-handbook.md`
- `specs/features/softos-engram-devcontainer-install-and-smoke.spec.md`

### Read paths obligatorios

- `AGENTS.md`
- `.agents/skills/softos-agent-playbook/SKILL.md`
- `.agents/skills/softos-agent-memory-playbook/SKILL.md`
- `.agents/skills/softos-release-manager/SKILL.md`
- `workspace.config.json`
- `workspace.capabilities.json`

### Out of scope explicito

- `gateway/**`
- repos de producto externos
- cambios en claim/plan/slices
- cambios en release promote
- servicios nuevos de base de datos

## Algoritmo

### Build del devcontainer

1. Resolver arquitectura Linux del contenedor.
2. Consultar el ultimo release de `Gentleman-Programming/engram`.
3. Seleccionar asset Linux compatible con `amd64` o `arm64`.
4. Descargar y extraer el binario.
5. Instalar `engram` en `/usr/local/bin/engram`.
6. Ejecutar `engram version` durante build para detectar instalacion rota.

### Runtime del workspace

1. El servicio `workspace` exporta `ENGRAM_PROJECT`.
2. El servicio `workspace` exporta `ENGRAM_DATA_DIR=/workspace/.flow/memory/engram`.
3. `flow memory doctor` crea el directorio si falta y reporta disponibilidad.
4. `flow memory smoke` ejecuta `engram version`, `engram stats` y `engram context <project>`.
5. `flow memory smoke --save` guarda una memoria estructurada pequena para validar escritura.

## Stop Conditions

- Si la descarga de release no encuentra asset Linux compatible, el build del devcontainer falla.
- Si `flow memory smoke` no encuentra `engram`, retorna codigo distinto de cero e indica reconstruir el devcontainer.
- Si `flow memory doctor` no encuentra `engram`, retorna cero y reporta `available=false`.
- Si una memoria contradice specs o CI, se ignora la memoria y se confia en el artefacto autoritativo.

## Slice Breakdown

```yaml
- name: engram-devcontainer-install-and-flow-memory
  targets:
    - ../../.devcontainer/Dockerfile
    - ../../.devcontainer/docker-compose.yml
    - ../../.gitignore
    - ../../.flow/memory/.gitkeep
    - ../../flow
    - ../../workspace.config.json
    - ../../flowctl/parser.py
    - ../../flowctl/memory_ops.py
    - ../../flowctl/test_memory_ops.py
    - ../../flowctl/test_agent_memory_capability.py
    - ../../capabilities/agent-memory-engram.capability.json
    - ../../.agents/skills/softos-agent-memory-playbook/SKILL.md
    - ../../docs/softos-agent-dev-handbook.md
    - ../../README.md
    - ../../specs/features/softos-engram-devcontainer-install-and-smoke.spec.md
  hot_area: agent memory devcontainer install
  depends_on: []
  slice_mode: minimal-change
  surface_policy: required
  minimum_valid_completion: Engram se instala en el devcontainer y flow memory valida storage aislado
  validated_noop_allowed: false
  acceptable_evidence:
    - Engram is installed by the devcontainer image build.
    - Workspace memory uses project-scoped ENGRAM_DATA_DIR.
    - flow memory doctor is non-blocking when Engram is absent.
    - flow memory smoke validates the installed binary and storage when Engram is present.
    - python3 -m unittest flowctl.test_memory_ops flowctl.test_agent_memory_capability
    - python3 ./flow ci spec specs/features/softos-engram-devcontainer-install-and-smoke.spec.md
    - python3 ./flow memory doctor --json
```

## Verification Matrix

```yaml
- name: memory-ops-unit
  level: custom
  command: python3 -m unittest flowctl.test_memory_ops
  blocking_on:
    - ci
  environments:
    - local
  notes: valida doctor no bloqueante, env por proyecto y smoke command sequence

- name: agent-memory-capability-unit
  level: custom
  command: python3 -m unittest flowctl.test_agent_memory_capability
  blocking_on:
    - ci
  environments:
    - local
  notes: valida capability, playbook e instalacion project-scoped en devcontainer

- name: spec-ci-engram-devcontainer
  level: custom
  command: python3 ./flow ci spec specs/features/softos-engram-devcontainer-install-and-smoke.spec.md
  blocking_on:
    - approval
  environments:
    - local
  notes: valida estructura, targets y verification matrix

- name: memory-doctor-local
  level: smoke
  command: python3 ./flow memory doctor --json
  blocking_on:
    - ci
  environments:
    - local
  notes: debe retornar cero incluso si host aun no tiene Engram instalado

- name: memory-smoke-devcontainer
  level: smoke
  command: scripts/workspace_exec.sh python3 ./flow memory smoke --json
  blocking_on:
    - ci
  environments:
    - devcontainer
  notes: valida Engram instalado dentro de workspace y storage aislado
```

## Acceptance Criteria

- `engram` se instala automaticamente al construir la imagen del devcontainer.
- `workspace` declara `ENGRAM_PROJECT` y `ENGRAM_DATA_DIR`.
- `.flow/memory/**` queda fuera de versionamiento.
- `flow memory doctor --json` reporta proyecto, data dir, db path y disponibilidad.
- `flow memory smoke --json` valida binario, stats y context dentro del contenedor.
- Tests unitarios y `flow ci spec` pasan.
- La release OSS publica el cambio con changelog, tag y GitHub Release.
