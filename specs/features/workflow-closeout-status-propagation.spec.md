---
schema_version: 3
name: "Workflow closeout and status propagation"
description: "Hacer que el cierre operativo de una feature en SoftOS propague estado real desde slice verify al plan, que workflow next-step deje de recomendar slices ya resueltas y que exista un cierre consolidado tipo close-feature con reporte final."
status: approved
owner: platform
single_slice_reason: ""
multi_domain: false
phases: []
depends_on:
  - specs/000-foundation/spec-as-source-operating-model.spec.md
  - specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - specs/000-foundation/repo-routing-and-worktree-orchestration.spec.md
required_runtimes: []
required_services: []
required_capabilities: []
stack_projects: []
stack_services: []
stack_capabilities: []
targets:
  - ../../flow
  - ../../flowctl/features.py
  - ../../flowctl/parser.py
  - ../../flowctl/workflows.py
  - ../../flowctl/test_*.py
  - ../../docs/**/*.md
  - ../../README.md
  - ../../specs/features/workflow-closeout-status-propagation.spec.md
---

# Workflow closeout and status propagation

## Objetivo

Corregir el cierre operativo de features en SoftOS para que el estado visible del workflow refleje
la evidencia real ya producida por `flow slice verify`, para que `workflow next-step` no recomiende
trabajo ya resuelto y para que exista un cierre consolidado de feature con reporte final.

## Contexto

Hoy SoftOS permite:

- crear y aprobar specs
- planear slices en `.flow/plans/<slug>.json`
- arrancar slices
- verificar slices con `flow slice verify`
- generar handoffs y reportes operativos

Sin embargo, el ciclo no cierra bien:

- `flow slice verify` genera evidencia pero no actualiza el `status` persistido de la slice en el plan
- `flow workflow next-step` sigue leyendo el plan estático y por eso recomienda arrancar slices ya implementadas y verificadas
- no existe un comando único para consolidar el cierre de una feature y dejar un reporte final reusable para commit, review o release

Esto rompe la trazabilidad operativa definida por las foundations del workspace: la evidencia existe,
pero el estado derivado no se propaga.

## Foundations Aplicables

- `specs/000-foundation/spec-as-source-operating-model.spec.md`
- `specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md`
- `specs/000-foundation/repo-routing-and-worktree-orchestration.spec.md`

## Domains Aplicables

- no aplica domain porque el cambio afecta el framework operativo del workspace y no introduce
  lenguaje de dominio de producto estable

## Problema a resolver

El estado operativo de una feature puede quedar inconsistente con la evidencia ya generada:

- un verification report exitoso no cambia el `status` de la slice
- `workflow next-step` no distingue entre slices pendientes y slices ya verificadas
- el operador no tiene un cierre formal para consolidar estado, verifications y artefactos de cierre

El resultado es drift operacional entre:

- `.flow/plans/**`
- `.flow/reports/**`
- la recomendación del CLI

## Alcance

### Incluye

- actualizar `flow slice verify` para propagar al plan el resultado de verificación de la slice
- definir cómo se mapea evidencia exitosa o fallida a estados operativos persistidos
- actualizar `workflow next-step` para que derive recomendaciones desde estado real y no solo desde el plan inicial
- agregar `flow workflow close-feature <slug>` para consolidar evidencia y dejar reporte final de cierre
- documentación del nuevo ciclo de cierre operativo

### No incluye

- cambiar el modelo de approval humano de specs o merges
- alterar el formato base de specs fuera de lo necesario para documentar el cierre operativo
- automatizar commits, merges o releases desde `close-feature`
- reinterpretar como éxito slices sin evidencia verificable

## Repos afectados

| Repo | Targets |
| --- | --- |
| `sdd-workspace-boilerplate` | `../../flow`, `../../flowctl/**`, `../../docs/**/*.md`, `../../specs/features/workflow-closeout-status-propagation.spec.md` |

## Resultado esperado

- cuando `flow slice verify` pasa, la slice queda marcada en el plan con estado operativo actualizado
- cuando `flow slice verify` falla, el plan registra el resultado sin declarar la slice como cerrada
- `workflow next-step` deja de sugerir `slice start` para slices ya verificadas con éxito
- existe `flow workflow close-feature <slug>` para validar el estado de todas las slices, consolidar evidencia y escribir reportes de cierre
- el operador puede distinguir claramente entre una feature `execution-ready`, `in-review`, `verification-complete` y `ready-for-merge`

## Reglas de negocio

- el plan sigue siendo el artefacto operativo principal para slices, pero debe reflejar estado derivado de evidencia real
- un verification report exitoso no debe perder el contexto del plan original; debe enriquecerlo
- `close-feature` no puede inventar éxito si falta evidencia para alguna slice requerida
- `close-feature` debe fallar si existen slices sin verification report o con último resultado fallido, salvo que la spec declare un no-op validado y esa evidencia exista
- `workflow next-step` debe priorizar trabajo pendiente real y omitir acciones ya satisfechas por evidencia persistida
- el cierre de feature no reemplaza gates humanos; solo consolida estado y evidencia técnica

## Modelo de estado propuesto

### Estado por slice

Cada slice en `.flow/plans/<slug>.json` debe poder reflejar al menos:

- `slice-ready`
- `implementing`
- `in-review`
- `verification-passed`
- `verification-failed`
- `closed`

Reglas mínimas:

- `flow slice start` sigue llevando la slice a un estado de ejecución
- `flow slice verify` con resultado exitoso la mueve al menos a `verification-passed`
- `flow workflow close-feature` puede promover slices verificadas a `closed` como parte del cierre consolidado

### Estado de feature

`workflow next-step` y `close-feature` deben derivar un estado agregado de la feature usando:

- frontmatter de la spec
- plan de slices
- reports de verificación
- resultados persistidos por slice

Estados agregados esperados:

- `execution-ready`
- `in-review`
- `verification-complete`
- `ready-for-merge`

No se requiere cambiar el frontmatter de la spec a `released` dentro de esta feature.

## Flujo principal

1. El operador ejecuta `python3 ./flow workflow execute-feature <slug> --start-slices --json`.
2. SoftOS materializa slices y plan operativo.
3. El implementador trabaja una slice.
4. El operador ejecuta `python3 ./flow slice verify <slug> <slice>`.
5. SoftOS actualiza el plan con el resultado de esa verificación y registra la ruta del reporte.
6. El operador ejecuta `python3 ./flow workflow next-step <slug> --json`.
7. SoftOS omite slices ya verificadas y recomienda solo trabajo pendiente real.
8. Cuando todas las slices requeridas tienen evidencia válida, el operador ejecuta `python3 ./flow workflow close-feature <slug> --json`.
9. SoftOS valida consistencia, consolida evidencia y escribe un closeout report final.

## Contrato funcional

### `flow slice verify`

Inputs:

- `slug`
- `slice`
- evidencia derivada del worktree y del runner de verificación actual

Outputs:

- verification report existente
- actualización persistida en `.flow/plans/<slug>.json`
- actualización del state de la feature si ya existe ese state

Side effects:

- la slice guarda `last_verification_report`
- la slice guarda `last_verification_result`
- la slice actualiza su `status`

### `flow workflow next-step`

Inputs:

- `slug`
- spec
- plan
- evidencia de verificación por slice

Outputs:

- recomendaciones consistentes con slices pendientes
- exclusión explícita de slices ya verificadas o cerradas
- resumen agregado del estado de la feature

### `flow workflow close-feature`

Inputs:

- `slug`
- spec
- plan
- reports de verificación

Outputs:

- validación de que todas las slices requeridas están cerrables
- reporte JSON y Markdown de cierre
- promoción de slices verificadas a `closed`
- estado agregado final de la feature para uso operativo

Errores esperados:

- feature sin plan
- slices sin verification report
- slices con verificación fallida
- slug inexistente
- inconsistencia entre plan y reports

## Observabilidad y artefactos

Se permite extender:

- `.flow/plans/<slug>.json`
- `.flow/state/<slug>.json`
- `.flow/reports/<slug>-<slice>-verification.md`
- `.flow/reports/workflows/<slug>-close-feature.json`
- `.flow/reports/workflows/<slug>-close-feature.md`

El nuevo comando no debe borrar reports previos; solo consolidarlos.

## Routing de implementacion

- todo el trabajo cae en el workspace root
- la logica de parser/dispatch puede vivir en `flow` y `flowctl/parser.py`
- la persistencia de estado y closeout puede vivir en `flowctl/features.py` o `flowctl/workflows.py`
- la documentacion operativa debe actualizar `README.md` o `docs/**` segun corresponda

## Slice Breakdown

```yaml
- name: slice-verify-status-propagation
  targets:
    - ../../flowctl/features.py
    - ../../flowctl/test_*.py
    - ../../docs/**/*.md
  hot_area: slice verification state persistence
  depends_on: []
  slice_mode: implementation-heavy
  surface_policy: required

- name: workflow-next-step-derived-status
  targets:
    - ../../flow
    - ../../flowctl/workflows.py
    - ../../flowctl/parser.py
    - ../../flowctl/test_*.py
  hot_area: workflow next-step orchestration
  depends_on:
    - slice-verify-status-propagation
  slice_mode: implementation-heavy
  surface_policy: required

- name: workflow-close-feature-command
  targets:
    - ../../flow
    - ../../flowctl/workflows.py
    - ../../flowctl/parser.py
    - ../../docs/**/*.md
    - ../../flowctl/test_*.py
  hot_area: workflow closeout orchestration
  depends_on:
    - workflow-next-step-derived-status
  slice_mode: implementation-heavy
  surface_policy: required
```

## Criterios de aceptacion

- `flow slice verify` actualiza el status de la slice en el plan cuando la verificación pasa
- `flow slice verify` registra resultado fallido sin marcar la slice como cerrada cuando la verificación falla
- `workflow next-step` no recomienda arrancar slices que ya tienen evidencia exitosa persistida
- `workflow next-step` expone un resumen agregado que refleje estado operacional real
- existe `flow workflow close-feature <slug>` y falla si faltan evidencias obligatorias
- `flow workflow close-feature <slug>` genera un reporte final reutilizable para review/commit
- el cierre consolidado no cambia gates humanos ni marca `released` por sí solo

## Verification Matrix

```yaml
- name: workflow-closeout-status-propagation-unit
  level: custom
  command: python3 -m unittest flowctl.test_slice_governance flowctl.test_workflows
  blocking_on:
    - ci
  environments:
    - local
  notes: valida propagacion de estado, derivacion de next-step y closeout command

- name: workflow-closeout-status-propagation-smoke
  level: integration
  command: python3 ./flow workflow intake closeout-smoke --title "Closeout smoke" --description "Smoke para cierre operativo" --acceptance-criteria "smoke" --json && python3 ./flow plan closeout-smoke && python3 ./flow workflow execute-feature closeout-smoke --start-slices --json
  blocking_on:
    - ci
  environments:
    - local
  notes: valida que la feature pueda llegar desde plan hasta cierre sin drift operativo
```

## Test plan

- tests unitarios para la mutación del plan desde `slice verify`
- tests unitarios para `workflow next-step` con slices mezcladas entre pendientes, verificadas y fallidas
- tests unitarios para `workflow close-feature`
- smoke manual o automatizado que verifique reportes de cierre reales en `.flow/reports/workflows/**`

## Rollout

- primero introducir propagación de estado por slice
- luego actualizar `next-step` para consumir ese estado derivado
- finalmente introducir `close-feature`

## Rollback

- si `close-feature` falla o introduce drift, el fallback permitido es seguir usando reports de verificación individuales
- no se deben borrar reports ni planes existentes al revertir; solo ignorar los campos nuevos si una reversión lo requiere
