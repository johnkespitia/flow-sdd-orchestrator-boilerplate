---
schema_version: 3
name: SoftOS Transversal Verification Matrix
description: Permitir que las specs declaren pruebas transversales ejecutables por nivel y que SoftOS las valide y consuma en CI y release verify
status: approved
owner: platform
single_slice_reason: ""
multi_domain: false
phases: []
depends_on:
  - ../../specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - ../../specs/features/spec-driven-delivery-bootstrap.spec.md
  - ../../specs/features/softos-quality-gates-traceability-and-risk.spec.md
required_runtimes:
  - python
required_services: []
required_capabilities: []
stack_projects: []
stack_services: []
stack_capabilities: []
targets:
  - ../../flow
  - ../../flowctl/**
  - ../../templates/root-feature.spec.md
  - ../../docs/softos-agent-dev-handbook.md
  - ../../docs/softos-full-workflow.md
  - ../../.agents/skills/softos-spec-definition-playbook/**
  - ../../specs/features/softos-transversal-verification-matrix.spec.md
---

# SoftOS Transversal Verification Matrix

## Objetivo

Permitir que una spec declare pruebas transversales ejecutables, por nivel y por etapa, para que SoftOS pueda tratarlas como contrato verificable y no solo como nota informal.

## Contexto

- Hoy SoftOS valida principalmente `[@test]` ligados a repos y runners locales.
- Eso cubre bien pruebas de slice y repo, pero no modela con suficiente precisión smoke, integración, api-contract o e2e que atraviesan varios repos o superficies.
- Las specs necesitan una forma explícita de declarar qué prueba transversal aplica, cuándo bloquea y qué comando produce evidencia.

## Foundations Aplicables

- spec foundation requerida: `specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md`
- esta feature amplía la capa de evidencia y quality gates del control plane

## Domains Aplicables

- no aplica domain porque el alcance es control plane transversal de SoftOS y no un dominio funcional de producto

## Problema a resolver

- una spec puede prometer comportamiento transversal sin declarar la prueba que lo verifica
- `[@test]` no distingue entre prueba local y verificación transversal bloqueante
- `release verify` no consume hoy una matriz explícita de verificación por feature

## Alcance

### Incluye

- una sección opcional pero estructurada `## Verification Matrix` en specs feature
- parser y validación estructural en `flowctl/specs.py`
- findings de review/CI para matrices inválidas
- propagación de perfiles al manifest de release
- ejecución en `release verify` de perfiles con `blocking_on: release`
- actualización de template y playbook para futuras specs

### No incluye

- inferencia automática completa de qué pruebas transversales requiere cada dominio
- orquestación distribuida de runners externos
- reemplazo de `[@test]` para pruebas locales de repo

## Repos afectados

| Repo | Targets |
| --- | --- |
| `sdd-workspace-boilerplate` | `../../flow`, `../../flowctl/**`, `../../templates/root-feature.spec.md`, `../../docs/**`, `../../.agents/skills/softos-spec-definition-playbook/**` |

## Resultado esperado

- una spec puede declarar perfiles transversales con nivel, comando, etapa bloqueante y entornos aplicables
- `flow ci spec` detecta matrices inválidas
- `flow release verify` ejecuta perfiles release-blocking y falla si la verificación transversal falla
- el template de feature deja visible la matriz como parte estándar del contrato

## Reglas de negocio

- `[@test]` sigue cubriendo pruebas locales de repo o slice
- `Verification Matrix` cubre pruebas transversales o gates adicionales
- cada perfil debe declarar `name`, `level`, `command` y `blocking_on`
- `blocking_on` solo puede usar `review`, `approval`, `ci` o `release`
- `release verify` solo ejecuta perfiles cuyo `blocking_on` incluya `release`
- si un perfil declara `environments`, solo aplica en esos entornos

## Flujo principal

1. una feature spec declara `## Verification Matrix` con un bloque YAML
2. `flow spec review` y `flow ci spec` validan la estructura
3. `flow release cut` incorpora los perfiles al manifest
4. `flow release verify` ejecuta los perfiles release-blocking aplicables al entorno
5. la evidencia queda en el payload de verificación del release

## Contrato funcional

- sección `## Verification Matrix` con bloque YAML de lista
- cada item acepta:
  - `name`
  - `level`
  - `command`
  - `blocking_on`
  - `environments` opcional
  - `notes` opcional
- niveles válidos iniciales:
  - `integration`
  - `api-contract`
  - `e2e`
  - `smoke`
  - `migration`
  - `security`
  - `performance`
  - `custom`

## Routing de implementacion

- el parser vive en `flowctl/specs.py`
- `flow ci spec` y `flow spec review` consumen el análisis extendido
- `release cut` y `release verify` consumen la matriz serializada en el manifest
- la plantilla y el playbook gobiernan adopción futura

## Slice Breakdown

```yaml
- name: parser-and-ci-contract
  targets:
    - ../../flow
    - ../../flowctl/**
  hot_area: flowctl/spec-verification-matrix
  depends_on: []
- name: release-consumption
  targets:
    - ../../flow
    - ../../flowctl/**
  hot_area: flowctl/release-verification
  depends_on:
    - parser-and-ci-contract
- name: template-and-playbook-adoption
  targets:
    - ../../templates/root-feature.spec.md
    - ../../docs/softos-agent-dev-handbook.md
    - ../../docs/softos-full-workflow.md
    - ../../.agents/skills/softos-spec-definition-playbook/**
    - ../../specs/features/softos-transversal-verification-matrix.spec.md
  hot_area: docs/verification-matrix
  depends_on:
    - release-consumption
```

## Criterios de aceptacion

- existe soporte para `## Verification Matrix` en el análisis de specs
- `flow ci spec` falla ante matrices inválidas
- `flow spec review` reporta el conteo de perfiles de verificación transversal
- `flow release cut` serializa la matriz por feature en el manifest
- `flow release verify` ejecuta perfiles `blocking_on: release`
- el template de feature incluye una sección `## Verification Matrix`
- el playbook de definición de specs instruye cuándo usar la matriz

## Test plan

- [@test] ../../flowctl/test_verification_matrix.py
- [@test] ../../flowctl/test_release_verify_matrix.py

## Rollout

- introducir la matriz como capacidad del boilerplate
- usarla primero en specs que toquen API, integración o flujos cross-repo
- endurecer su obligatoriedad por heurística en una iteración posterior si hace falta

## Rollback

- revertir parser, template y consumo de release verify
- mantener `[@test]` como contrato mínimo mientras se reevalúa la capacidad
