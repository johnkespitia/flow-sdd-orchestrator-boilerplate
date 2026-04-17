---
schema_version: 3
name: "SoftOS scope drift release enforcement"
description: "Bloquear release cut cuando la evidencia de slice muestra cambios fuera de targets o tests aprobados por la spec."
status: approved
owner: platform
single_slice_reason: "release scope drift enforcement is a bounded gate over existing slice verification and release cut"
multi_domain: false
phases: []
depends_on:
  - specs/000-foundation/spec-as-source-operating-model.spec.md
  - specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - specs/000-foundation/repo-routing-and-worktree-orchestration.spec.md
  - specs/features/softos-spec-approval-formal-gate.spec.md
  - specs/features/softos-plan-approval-formal-gate.spec.md
  - specs/features/softos-central-policy-check.spec.md
  - specs/features/softos-evidence-bundle-status.spec.md
required_runtimes: []
required_services: []
required_capabilities: []
stack_projects: []
stack_services: []
stack_capabilities: []
targets:
  - ../../flowctl/features.py
  - ../../flowctl/release.py
  - ../../flowctl/test_release_scope_drift.py
  - ../../README.md
  - ../../docs/softos-agent-dev-handbook.md
  - ../../specs/features/softos-scope-drift-release-enforcement.spec.md
---

# SoftOS scope drift release enforcement

## Objetivo

Cerrar v0.10.3 agregando un gate binario antes de `release cut`: una feature solo puede entrar a release si las slices verificadas registran su inventario de archivos cambiados y esos archivos estan cubiertos por los `targets` o `[@test]` aprobados por la spec.

## Contexto actual

- `slice verify` ya inspecciona el diff del worktree y falla si una slice toca archivos fuera de sus owned targets o linked tests.
- `release cut` exige plan, estado aprobado y reportes de verificacion, pero antes de esta spec no revalidaba el inventario de cambios contra el alcance global de la spec.
- Una verificacion antigua podia no contener `changed_files`, lo que impide probar ausencia de scope drift en el momento de release.

## Governing Decision

- `release cut` es el punto obligatorio de enforcement pre-release para specs operacionales.
- El gate usa evidencia persistida por `slice verify`; no reinterpreta el chat ni la intencion del agente.
- Si una slice fue verificada antes de existir el inventario `changed_files`, el release queda bloqueado hasta repetir `slice verify`.
- Los archivos permitidos son exactamente los patrones declarados en `targets` y `[@test]` de la spec aprobada para el repo de la slice.
- El gate no cambia `release publish`, que sigue siendo la capa de release OSS del repo.

## Executable Surface Inventory

| Superficie | Cambio obligatorio | Prohibido |
|---|---|---|
| `flowctl/features.py` | Persistir `changed_files`, owned patterns y linked tests en `slice_results`. | Relajar el fallo existente de diff fuera de scope durante `slice verify`. |
| `flowctl/release.py` | Bloquear `release cut` si falta inventario o si hay archivos fuera de targets/tests aprobados. | Permitir bypass silencioso para verificaciones legacy. |
| Tests | Cubrir caso permitido, caso drift y caso verificacion legacy sin `changed_files`. | Depender de Git real o de `.flow` real. |
| Docs | Explicar que `release cut` exige verificaciones recientes con inventario de archivos. | Prometer enforcement para `release publish`. |

## Algorithm

1. `slice verify` calcula `changed_files` desde el worktree inspeccionado.
2. `slice verify` persiste en `.flow/state/<slug>.json`:
   - `changed_files`;
   - `owned_patterns`;
   - `linked_test_patterns`;
   - `materialized_tests`.
3. `release cut` carga spec, plan y state como ya lo hace.
4. Para cada slice del plan:
   - exigir `slice_results[<slice>].changed_files`;
   - resolver repo desde resultado de slice o plan;
   - construir patrones permitidos desde `analysis.target_index[repo]` y `analysis.test_index[repo]`;
   - comparar cada archivo cambiado con `fnmatch`;
   - acumular findings si no matchea.
5. Si hay findings, abortar antes de escribir manifest.
6. Si no hay findings, continuar con el flujo existente de manifest, dirty tree check y release candidate state.

## Stop Conditions

- Falta plan JSON: bloquear release.
- Plan sin slices verificables: bloquear release.
- Slice sin `slice_results`: bloquear release.
- Slice sin `changed_files`: bloquear release y pedir repetir `slice verify`.
- Slice con repo ausente: bloquear release.
- Spec sin targets/tests para el repo de la slice: bloquear release.
- Cualquier archivo cambiado fuera de targets/tests aprobados: bloquear release.

## Slice Breakdown

```yaml
- name: release-scope-drift-gate
  targets:
    - ../../flowctl/features.py
    - ../../flowctl/release.py
    - ../../flowctl/test_release_scope_drift.py
    - ../../README.md
    - ../../docs/softos-agent-dev-handbook.md
    - ../../specs/features/softos-scope-drift-release-enforcement.spec.md
  hot_area: release cut governance
  depends_on: []
  slice_mode: governance
  surface_policy: required
  minimum_valid_completion: release cut blocks missing changed_files and out-of-scope changed files before manifest creation
  validated_noop_allowed: false
  acceptable_evidence:
    - python3 -m pytest -q flowctl/test_release_scope_drift.py
    - python3 -m unittest flowctl.test_release_publish
    - python3 ./flow ci spec specs/features/softos-scope-drift-release-enforcement.spec.md
```

## Verification Matrix

```yaml
- name: release-scope-drift-unit
  level: custom
  command: python3 -m pytest -q flowctl/test_release_scope_drift.py
  blocking_on:
    - ci
  environments:
    - local
  notes: valida allowlist, drift y verificacion legacy sin changed_files

- name: release-publish-regression
  level: custom
  command: python3 -m unittest flowctl.test_release_publish
  blocking_on:
    - ci
  environments:
    - local
  notes: valida que release publish OSS no se vea afectado

- name: spec-ci-scope-drift
  level: custom
  command: python3 ./flow ci spec specs/features/softos-scope-drift-release-enforcement.spec.md
  blocking_on:
    - approval
  environments:
    - local
  notes: valida targets, dependencias y estructura de spec
```

## Acceptance Criteria

- `slice verify` persiste `changed_files` en `slice_results`.
- `release cut` aborta si una slice verificada no trae inventario `changed_files`.
- `release cut` aborta si una slice cambio archivos fuera de `targets` o `[@test]` aprobados.
- `release cut` permite continuar cuando todos los cambios verificados estan dentro del alcance aprobado.
- La documentacion operativa indica que las verificaciones deben ser recientes antes de release.
