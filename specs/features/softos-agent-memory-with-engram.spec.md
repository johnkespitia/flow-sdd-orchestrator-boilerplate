---
schema_version: 3
name: "SoftOS agent memory with Engram"
description: "Introducir Engram como capacidad opcional y consultiva de memoria para agentes SoftOS, empezando por playbook, capability y evidencia de uso, sin acoplar el core ni convertir memorias en fuente de verdad."
status: approved
owner: platform
single_slice_reason: "memory bootstrap is intentionally narrow but split into capability, playbook and docs slices"
multi_domain: false
phases: []
depends_on:
  - specs/000-foundation/spec-as-source-operating-model.spec.md
  - specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - specs/000-foundation/repo-routing-and-worktree-orchestration.spec.md
required_runtimes: []
required_services: []
required_capabilities:
  - agent-memory-engram
stack_projects: []
stack_services: []
stack_capabilities: []
targets:
  - ../../capabilities/agent-memory-engram.capability.json
  - ../../workspace.capabilities.json
  - ../../.agents/skills/softos-agent-memory-playbook/SKILL.md
  - ../../docs/softos-agent-dev-handbook.md
  - ../../README.md
  - ../../specs/features/softos-agent-memory-with-engram.spec.md
---

# SoftOS agent memory with Engram

## Objetivo

Agregar una primera ola reversible de memoria para agentes usando Engram como herramienta
local-first y consultiva.

La ola debe permitir que agentes recuerden aprendizajes reutilizables entre sesiones sin cambiar
la fuente de verdad del SDLC ni volver obligatoria la memoria para ejecutar SoftOS.

## Contexto

SoftOS ya tiene fuentes autoritativas fuertes:

- `specs/**`
- `AGENTS.md`
- `workspace.config.json`
- `.flow/reports/**`
- release manifests/promotions
- CI y verification matrix

El problema no es falta de verdad canónica. El problema es que los agentes pierden aprendizajes
entre sesiones y vuelven a descubrir gotchas ya resueltos:

- formato YAML requerido para `Slice Breakdown`
- auth de `gh` dentro del devcontainer
- límites de `claim -> plan`
- comandos exactos de smoke
- patrones de hardening por spec family

Engram encaja como memoria consultiva porque ofrece MCP/CLI sobre storage local, pero no debe
convertirse en contrato del sistema.

## Foundations Aplicables

- `spec-as-source-operating-model`
  las specs siguen siendo la fuente de verdad; memoria solo aporta contexto
- `spec-driven-delivery-and-infrastructure`
  CI, release y reports siguen siendo los gates verificables
- `repo-routing-and-worktree-orchestration`
  la memoria no puede modificar routing ni ownership de targets

## Domains Aplicables

- no aplica domain porque la feature pertenece al plano de operación de agentes

## Governing Decision

- Engram será capability opcional, no requisito global
- la integración inicial será playbook + capability + documentación
- no se agregará dependencia obligatoria al core `flow`
- no se guardarán secretos ni datos sensibles
- no se usará memoria para saltar `flow spec review`, `flow ci`, `flow release` ni gates humanos

## Alcance

### Incluye

- capability `agent-memory-engram`
- skill `softos-agent-memory-playbook`
- reglas de uso seguro para recall/save
- contrato de fuente consultiva vs autoritativa
- criterios para decidir si escalar luego a Graphiti/Zep

### No incluye

- instalación automática de Engram
- MCP server obligatorio en devcontainer
- comandos `flow memory`
- sync de memorias al repo
- knowledge graph temporal
- persistencia automática de todos los logs de agentes

## Resultado esperado

- un agente puede consultar memoria al iniciar tareas SoftOS
- un agente puede guardar outcomes reutilizables al cerrar tareas
- si Engram no está instalado, el SDLC sigue funcionando
- el equipo puede evaluar con evidencia si conviene escalar a Graphiti/Zep después

## Execution Surface Inventory

### Write paths obligatorios

- `capabilities/agent-memory-engram.capability.json`
- `workspace.capabilities.json`
- `.agents/skills/softos-agent-memory-playbook/SKILL.md`
- `README.md`
- `docs/softos-agent-dev-handbook.md`
- `specs/features/softos-agent-memory-with-engram.spec.md`

### Read paths obligatorios

- `AGENTS.md`
- `.agents/skills/softos-agent-playbook/SKILL.md`
- `.agents/skills/softos-spec-definition-playbook/SKILL.md`
- `.agents/skills/softos-reference-spec-hardening/SKILL.md`
- `.agents/skills/softos-release-manager/SKILL.md`

### Out of scope explícito

- `flowctl/**`
- `.devcontainer/**`
- `gateway/**`
- runtime services nuevos
- Graphiti/Zep

## Reglas de negocio

- memoria nunca es autoritativa
- memoria no bloquea ejecución si falta Engram
- cada memoria guardada debe tener propósito reusable
- memorias deben tener proyecto/área/evidencia cuando aplique
- memorias obsoletas se corrigen con nueva evidencia, no con silencio
- no se guarda output bruto de herramientas sin resumen humano/agente
- no se guardan secretos bajo ninguna circunstancia

## Uso esperado

### Inicio de tarea

1. Identificar spec, repo, runtime o hot_area.
2. Consultar memoria por contexto relevante.
3. Leer specs/AGENTS/playbooks actuales.
4. Usar memoria solo como guía de descubrimiento.

### Cierre de tarea

1. Ejecutar evidencia requerida por spec.
2. Identificar aprendizajes reutilizables.
3. Guardar memoria estructurada si aporta valor futuro.
4. Referenciar archivos/commands, no contenido sensible.

## Evaluación para escalar a Graphiti/Zep

Escalar solo si, después de usar Engram, aparecen necesidades reales de:

- relaciones temporales entre specs, releases, claims y decisiones
- consultas tipo grafo entre módulos, incidentes y rollouts
- historial de ownership por agente/entorno
- memoria multi-workspace con retención y auditoría central

No escalar por preferencia tecnológica sin evidencia de uso.

## Verification Matrix

```yaml
- name: spec-ci-agent-memory-engram
  level: custom
  command: python3 ./flow ci spec specs/features/softos-agent-memory-with-engram.spec.md
  blocking_on:
    - approval
  environments:
    - local
  notes: valida estructura de la spec y contratos de capability/skill

- name: agent-memory-capability-unit
  level: custom
  command: python3 -m unittest flowctl.test_agent_memory_capability
  blocking_on:
    - ci
  environments:
    - local
  notes: valida que `agent-memory-engram` este registrado y resuelva su capability pack
```

## Smoke Manual Futuro

Cuando Engram esté instalado localmente, el smoke no bloqueante recomendado es:

```bash
engram context softos-sdd-orchestrator
engram search "softos gateway release gotcha"
engram save softos-sdd-orchestrator "TYPE: outcome
Project: softos-sdd-orchestrator
Area: smoke
What: Engram memory smoke completed
Why: Validate optional agent memory workflow
Where: docs/softos-agent-dev-handbook.md
Evidence: engram context/search/save
Learned: Engram is consultive and does not block SoftOS when unavailable"
```

Este smoke no debe agregarse como gate obligatorio mientras Engram siga siendo opcional.

## Acceptance Criteria

- existe capability `agent-memory-engram`
- `workspace.capabilities.json` registra la capability como habilitada
- existe skill `softos-agent-memory-playbook`
- la spec declara memoria como consultiva y opcional
- quedan definidos criterios para evaluar Graphiti/Zep como ola posterior

## Slice Breakdown

```yaml
- name: agent-memory-capability-contract
  targets:
    - ../../capabilities/agent-memory-engram.capability.json
    - ../../workspace.capabilities.json
    - ../../specs/features/softos-agent-memory-with-engram.spec.md
  hot_area: agent memory capability
  depends_on: []
  slice_mode: governance
  surface_policy: required
  minimum_valid_completion: capability registrada y spec aprobada con frontera consultiva clara
  validated_noop_allowed: false
  acceptable_evidence:
    - python3 ./flow ci spec specs/features/softos-agent-memory-with-engram.spec.md

- name: agent-memory-playbook
  targets:
    - ../../.agents/skills/softos-agent-memory-playbook/SKILL.md
  hot_area: agent memory playbook
  depends_on:
    - agent-memory-capability-contract
  slice_mode: minimal-change
  surface_policy: required
  minimum_valid_completion: playbook define recall/save, no-secret policy y boundary autoritativo
  validated_noop_allowed: false
  acceptable_evidence:
    - skill documentado y linkeado desde README o handbook

- name: agent-memory-docs
  targets:
    - ../../README.md
    - ../../docs/softos-agent-dev-handbook.md
  hot_area: agent memory docs
  depends_on:
    - agent-memory-playbook
  slice_mode: minimal-change
  surface_policy: required
  minimum_valid_completion: README y handbook describen Engram como memoria opcional y consultiva
  validated_noop_allowed: false
  acceptable_evidence:
    - docs enlazan el playbook y preservan la frontera source-of-truth
```
