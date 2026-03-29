---
schema_version: 3
name: SoftOS Frontmatter Release Status Alignment
description: Alinear el frontmatter de las specs con el estado operativo released para evitar dobles verdades entre YAML y .flow/state
status: approved
owner: platform
single_slice_reason: El cambio toca un unico hot area semantico compartido entre gobernanza de specs, release y workflow; dividirlo aumentaria riesgo de inconsistencias de estado.
multi_domain: false
phases:
  - foundation
  - release
depends_on:
  - ../../specs/000-foundation/spec-as-source-operating-model.spec.md
  - ../../specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - ../../specs/features/softos-program-closure-and-operational-readiness.spec.md
required_runtimes:
  - python
required_services: []
required_capabilities: []
stack_projects: []
stack_services: []
stack_capabilities: []
targets:
  - ../../flow
  - ../../flowctl/specs.py
  - ../../flowctl/ci.py
  - ../../flowctl/features.py
  - ../../flowctl/workflows.py
  - ../../flowctl/release.py
  - ../../flowctl/infra.py
  - ../../flowctl/stack_design.py
  - ../../flowctl/test_ci_spec.py
  - ../../flowctl/test_release_verify.py
  - ../../docs/spec-driven-sdlc-map.md
  - ../../docs/softos-agent-dev-handbook.md
---

# SoftOS Frontmatter Release Status Alignment

## Objetivo

Eliminar la inconsistencia entre el frontmatter de una spec y el estado operativo en `.flow/state/**`, de forma que una feature liberada quede marcada como `released` tambien en su YAML sin permitir re-ejecucion accidental de planning o delivery.

## Contexto

- Hoy SoftOS ya usa `released` como estado terminal en `.flow/state/**`.
- Sin embargo, varias rutas de CI, dependencies, planning y docs siguen tratando `approved` como unico estado valido del frontmatter.
- Eso deja una doble verdad: una spec puede estar realmente liberada en el estado operativo y seguir viendose como `approved` en el archivo versionado.
- El problema ya aparecio al cerrar `softos-program-closure-and-operational-readiness`: el release estaba completo, pero el YAML seguia sugiriendo que la spec aun estaba solo aprobada.

## Foundations Aplicables

- `../../specs/000-foundation/spec-as-source-operating-model.spec.md`: la spec debe seguir siendo fuente de verdad tambien para el estado terminal observable.
- `../../specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md`: los gates y el flujo de release deben mantener semantica consistente en CI, workflow y release automation.

## Domains Aplicables

- no aplica domain porque este cambio pertenece al control plane transversal de SoftOS y no a un dominio funcional en `specs/domains/**`

## Problema a resolver

- El frontmatter `status` y `.flow/state.status` pueden divergir despues de un release exitoso.
- `ci spec` y otras validaciones tratan `released` como no listo o simplemente no contemplado.
- `workflow next-step` y comandos de planning pueden seguir sugiriendo acciones sobre una feature ya liberada.
- `release verify` y `release promote` no garantizan que el archivo de la spec quede alineado con el estado terminal publicado.

## Alcance

### Incluye

- helper explicito de semantica de estados de frontmatter
- aceptar `released` como estado valido para CI estricto y resolucion de dependencias
- bloquear re-ejecucion de planning/execute-feature/infra/stack sobre specs ya liberadas
- actualizar `release promote` para reflejar `released` tambien en el frontmatter cuando la promocion a production verifica correctamente
- cobertura de tests para las nuevas reglas de estado
- documentacion del flujo SDLC y handbook para dejar claro el modelo final

### No incluye

- cambiar el significado de `draft` o `approved`
- introducir nuevos estados intermedios
- reabrir automaticamente una spec `released`
- migracion masiva retroactiva de todas las specs historicas en este mismo incremento

## Repos afectados

| Repo | Targets |
| --- | --- |
| `sdd-workspace-boilerplate` | `../../flow`, `../../flowctl/specs.py`, `../../flowctl/ci.py`, `../../flowctl/features.py`, `../../flowctl/workflows.py`, `../../flowctl/release.py`, `../../flowctl/infra.py`, `../../flowctl/stack_design.py`, `../../flowctl/test_ci_spec.py`, `../../flowctl/test_release_verify.py`, `../../docs/spec-driven-sdlc-map.md`, `../../docs/softos-agent-dev-handbook.md` |

## Resultado esperado

- Una spec en `released` pasa gates de lectura y trazabilidad donde corresponde.
- Una spec en `released` no vuelve a entrar en planning ni en ejecucion.
- `release promote --env production` deja alineados el estado operativo y el frontmatter.
- El modelo queda documentado como semantica oficial del sistema.

## Reglas de negocio

- `approved` sigue siendo el unico estado ejecutable para planning y release cut.
- `released` es un estado terminal valido para lectura, CI estricto y dependencias ya satisfechas.
- Ningun comando de planning o materializacion debe reusar una spec en `released`.
- La transicion de `approved` a `released` solo puede ocurrir despues de una promocion a production con verificacion `passed`.
- El sistema no debe requerir ediciones manuales del YAML para reflejar un release exitoso.

## Flujo principal

1. Una spec se crea y aprueba en `draft -> approved`.
2. La feature se planifica, ejecuta y pasa sus gates normales.
3. `flow release cut` solo incluye specs aun ejecutables (`approved` y no ya liberadas por estado operativo).
4. `flow release promote --env production` verifica el release.
5. Si la verificacion pasa, SoftOS actualiza `.flow/state.status = released` y tambien `frontmatter.status = released`.
6. Desde ese momento, `workflow next-step` reporta estado terminal y planning/execute-feature quedan bloqueados.

## Contrato funcional

- Inputs clave:
  - `frontmatter.status`
  - `.flow/state.status`
  - resultado de `release promote` + `release verify`
- Outputs clave:
  - `ci spec` acepta `released`
  - dependencies aceptan `released`
  - planning/workflow rechazan `released`
  - `release promote` deja YAML y estado operativo alineados
- Errores esperados:
  - intentar planear una spec ya `released`
  - intentar re-ejecutar una feature ya `released`
  - promover sin verificacion satisfactoria
- Side effects relevantes:
  - actualizacion del archivo `.spec.md`
  - actualizacion del archivo `.flow/state/<slug>.json`

## Routing de implementacion

- `flowctl/specs.py` define la semantica de estados compartida.
- `flowctl/ci.py` aplica la regla de CI estricto.
- `flowctl/features.py`, `flowctl/workflows.py`, `flowctl/infra.py` y `flowctl/stack_design.py` bloquean re-ejecucion sobre `released`.
- `flowctl/release.py` y `flow` sincronizan release operativo y frontmatter.
- `docs/**` documenta el modelo oficial.

## Slice Breakdown

```yaml
- name: frontmatter-release-status-alignment
  targets:
    - ../../flow
    - ../../flowctl/specs.py
    - ../../flowctl/ci.py
    - ../../flowctl/features.py
    - ../../flowctl/workflows.py
    - ../../flowctl/release.py
    - ../../flowctl/infra.py
    - ../../flowctl/stack_design.py
    - ../../flowctl/test_ci_spec.py
    - ../../flowctl/test_release_verify.py
    - ../../docs/spec-driven-sdlc-map.md
    - ../../docs/softos-agent-dev-handbook.md
  hot_area: flowctl/status-model
  depends_on: []
```

## Criterios de aceptacion

- `ci spec` trata `released` como estado valido en modo estricto.
- `depends_on` acepta specs en `approved` o `released`.
- `plan`, `workflow execute-feature`, `infra plan` y materializacion de stack rechazan specs `released`.
- `workflow next-step` informa estado terminal para una feature ya liberada.
- `release promote --env production` actualiza tambien el frontmatter a `released` cuando la verificacion pasa.
- La documentacion oficial del SDLC deja claro que `released` es el estado terminal versionado.

## Test plan

- [@test] ../../flowctl/test_ci_spec.py
- [@test] ../../flowctl/test_release_verify.py

## Rollout

- aplicar primero en el control plane base
- volver a promover una feature ya cerrada para validar que el frontmatter quede alineado
- usar este cambio como patron para futuras liberaciones

## Rollback

- revertir la semantica compartida de estados si aparece un caso no contemplado
- no borrar artefactos de release ya emitidos
- si una spec queda marcada incorrectamente como `released`, reabrirla con cambio versionado explicito
