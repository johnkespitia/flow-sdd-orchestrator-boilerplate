---
schema_version: 3
name: <Feature Name>
description: <Descripcion breve y concreta>
status: draft
owner: platform
single_slice_reason: ""
multi_domain: false
phases: []
depends_on: []
required_runtimes: []
required_services: []
required_capabilities: []
# Example:
# stack_projects:
#   - name: api
#     runtime: go-api
#     path: api
#     repo_code: api
#     compose_service: api
#     port: 8080
#     service_bindings: [postgres]
#     env:
#       DATABASE_URL: postgres://app:app@postgres:5432/app_dev?sslmode=disable
stack_projects: []
# Example:
# stack_services:
#   - name: postgres
#     runtime: postgres-service
#     env:
#       POSTGRES_DB: app_dev
#     volumes:
#       - workspace-postgres-data:/var/lib/postgresql/data
stack_services: []
stack_capabilities: []
targets:
  - ../../<implementation-repo>/app/**
  - ../../<implementation-repo>/tests/**
---

# <Feature Name>

## Objetivo

Describir el comportamiento observable que esta feature debe introducir en el sistema.

## Contexto

- por que existe ahora
- que foundations gobiernan esta feature
- que domains gobiernan esta feature
- si afecta backend, frontend o ambos
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

- <item>
- <item>

### No incluye

- <item>
- <item>

## Repos afectados

| Repo | Targets |
| --- | --- |
| `<implementation-repo>` | `../../<implementation-repo>/...` |
| `<other-repo>` | `../../<other-repo>/...` |

## Resultado esperado

- <resultado>

## Reglas de negocio

- <regla>

## Flujo principal

1. <paso>
2. <paso>
3. <paso>

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

## Slice Breakdown

```yaml
- name: <slice-name>
  targets:
    - ../../<implementation-repo>/app/**
  hot_area: <implementation-repo>/app
  depends_on: []
```

## Criterios de aceptacion

- <criterio>
- <criterio>

## Test plan

- [@test] ../../<implementation-repo>/tests/...

## Rollout

- <estrategia>

## Rollback

- <estrategia>
