---
schema_version: 2
name: Stack Bootstrap
description: TODO describir el resultado observable
status: draft
owner: platform
depends_on: []
required_runtimes: []
required_services: []
required_capabilities: []
stack_projects: []
stack_services: []
stack_capabilities: []
targets:
- ../../specs/**/*.spec.md
- ../../docs/**/*.md
- ../../flow
- ../../workspace.config.json
- ../../workspace.stack.json
---

# Stack Bootstrap

## Objetivo

Describir el stack que debe quedar materializado desde esta spec antes de entrar a implementación detallada.

## Prompt original

> quiero una aplicacion web en node con nextjs y typescript

## Contexto

- esta spec nace desde una inferencia asistida y debe ser revisada por un humano o cliente IA
- la topología declarativa del stack vive en el frontmatter, no en `workspace.stack.json`
- el manifest del stack se derivará solo después de aprobar esta spec

## Problema a resolver

- describir por que se necesita este stack ahora
- describir que foundations o dependencias deben existir antes de implementarlo

## Topología propuesta

Revisar y confirmar en frontmatter: `repo_code`, `compose_service`, `port`, `env`, `service_bindings`, `ports` y `volumes`.

### Proyectos

- TODO completar proyectos a materializar

### Servicios

- sin servicios inferidos

### Capabilities

- sin capabilities inferidas

## Alcance

### Incluye

- revisar y completar la topología declarada en el frontmatter
- aprobar la spec antes de derivar `workspace.stack.json`

### No incluye

- implementar comportamiento de negocio detallado dentro de los repos nuevos
- aprobar foundations generadas automáticamente sin review explícita

## Repos afectados

| Repo | Targets |
| --- | --- |
| `sdd-workspace-boilerplate` | ../../specs/**/*.spec.md, ../../docs/**/*.md, ../../flow, ../../workspace.config.json, ../../workspace.stack.json |

## Resultado esperado

- TODO describir el stack observable que debe quedar listo tras `stack apply --spec`

## Reglas de negocio

- la spec aprobada es la fuente de verdad para la topología materializable
- `stack design --prompt` solo asiste el authoring del draft inicial

## Flujo principal

1. se redacta o corrige esta spec hasta dejarla lista para review
2. `spec review` valida dependencias, runtimes, servicios y capabilities declaradas
3. `stack design|plan|apply --spec` deriva y materializa el stack desde la spec aprobada

## Contrato funcional

- inputs clave: spec aprobada con `stack_projects`, `stack_services`, `stack_capabilities`
- outputs clave: `workspace.stack.json`, repos/proyectos materializados, foundations generadas
- errores esperados: runtimes faltantes, servicios no declarados, spec no aprobada
- side effects relevantes: cambios en `workspace.config.json`, compose y `specs/000-foundation/generated/**`

## Routing de implementacion

- El repo se deduce desde `targets`.
- Cada slice debe pertenecer a un solo repo.
- El plan operativo vive en `.flow/plans/**`.
- Las dependencias estructurales viven en el frontmatter y deben resolverse antes de aprobar.

## Criterios de aceptacion

- `python3 ./flow spec review stack-bootstrap` debe identificar gaps de la topología declarada
- `python3 ./flow stack plan --spec stack-bootstrap` debe describir el stack a crear solo después de aprobar la spec

## Test plan

- Evidencia de verificacion del workspace: review manual o check operativo.

## Rollout

- TODO describir cómo se adoptará este stack en el workspace

## Rollback

- TODO describir cómo revertir la materialización del stack si la spec cambia
