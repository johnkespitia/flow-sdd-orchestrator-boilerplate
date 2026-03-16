---
name: <Feature Name>
description: <Descripcion breve y concreta>
status: draft
owner: platform
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
- si afecta backend, frontend o ambos

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

## Criterios de aceptacion

- <criterio>
- <criterio>

## Test plan

- [@test] ../../<implementation-repo>/tests/...

## Rollout

- <estrategia>

## Rollback

- <estrategia>
