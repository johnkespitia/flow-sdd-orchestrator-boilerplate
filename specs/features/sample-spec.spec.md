---
schema_version: 2
name: "Sample Spec"
description: "TODO describir el resultado observable"
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

# Sample Spec

## Objetivo

Describir el comportamiento observable que esta feature debe introducir.

## Contexto

- por que existe ahora
- que foundations gobiernan esta feature
- que repos estan afectados
- que runtimes, servicios o capabilities deben existir para materializarla


## Foundations Aplicables

- spec foundation requerida: `specs/000-foundation/...`
- justificacion si no aplica alguna foundation relevante

## Domains Aplicables

- spec domain requerida: `specs/domains/...`
- si no aplica domain, declarar explicitamente: `no aplica domain porque <razon>`

## Problema a resolver

- que duele hoy
- que riesgo o ineficiencia se quiere eliminar


## Alcance

### Incluye

- TODO
- TODO

### No incluye

- TODO
- TODO

## Repos afectados

| Repo | Targets |
| --- | --- |
| `sdd-workspace-boilerplate` | ../../specs/**/*.spec.md, ../../docs/**/*.md, ../../flow, ../../workspace.config.json, ../../workspace.stack.json |

## Resultado esperado

- TODO

## Reglas de negocio

- TODO

## Flujo principal

1. TODO
2. TODO
3. TODO

## Contrato funcional

- inputs clave
- outputs clave
- errores esperados
- side effects relevantes

## Routing de implementacion

- El repo se deduce desde `targets`.
- Cada slice debe pertenecer a un solo repo.
- El plan operativo vive en `.flow/plans/**`.
- Las dependencias estructurales viven en el frontmatter y deben resolverse antes de aprobar.

## Criterios de aceptacion

- TODO
- TODO

## Test plan

- Evidencia de verificacion del workspace: review manual o check operativo.

## Rollout

- TODO

## Rollback

- TODO
