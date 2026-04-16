---
schema_version: 3
name: "SoftOS evidence bundle status"
description: "Agregar status y bundle de evidencia por spec para consolidar approvals, policy, planes y reportes operacionales."
status: approved
owner: platform
single_slice_reason: "evidence status and bundle are one bounded read-only reporting surface"
multi_domain: false
phases: []
depends_on:
  - specs/000-foundation/spec-as-source-operating-model.spec.md
  - specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - specs/features/softos-spec-approval-formal-gate.spec.md
  - specs/features/softos-plan-approval-formal-gate.spec.md
  - specs/features/softos-central-policy-check.spec.md
  - specs/features/softos-human-gated-workflow-runner.spec.md
required_runtimes: []
required_services: []
required_capabilities: []
stack_projects: []
stack_services: []
stack_capabilities: []
targets:
  - ../../flow
  - ../../flowctl/parser.py
  - ../../flowctl/evidence.py
  - ../../flowctl/test_evidence.py
  - ../../README.md
  - ../../docs/softos-agent-dev-handbook.md
  - ../../specs/features/softos-evidence-bundle-status.spec.md
---

# SoftOS evidence bundle status

## Objetivo

Agregar una superficie de evidencia por spec:

- `flow evidence status <spec> --json`
- `flow evidence bundle <spec> --json`

El objetivo es responder si una spec tiene evidencia suficiente para avanzar a cierre/release y producir un bundle transportable de reportes.

## Contexto actual

- Los reportes ya existen en `.flow/reports/**`.
- Los approvals formales viven en `.flow/state/<slug>.json`.
- El policy central decide si stages sensibles estan permitidos.
- Falta una vista unica para handoffs, auditoria y cierre.

## Governing Decision

- Evidence no aprueba ni modifica specs.
- Evidence no reemplaza `flow ci`, `flow policy check` ni `release verify`.
- Evidence consolida estado y reportes existentes.
- `status` puede salir con codigo `2` si la evidencia no esta completa.
- `bundle` escribe artefactos bajo `.flow/reports/evidence/` aun cuando el estado no este listo.

## Executable Surface Inventory

| Superficie | Cambio obligatorio | Prohibido |
|---|---|---|
| `flowctl/evidence.py` | Agregar payload de status, scanner de reportes y escritura de bundle. | Ejecutar tests o CI desde evidence. |
| `flowctl/parser.py` | Agregar `flow evidence status` y `flow evidence bundle`. | Cambiar comandos `status`, `policy` o `workflow`. |
| `flow` | Registrar wrappers y crear `.flow/reports/evidence`. | Duplicar logica de approval/policy. |
| Tests | Cubrir missing evidence y copia de reportes al bundle. | Depender de `.flow` real del repo. |
| Docs | Mostrar evidence en el flujo recomendado. | Prometer production readiness sin release verification. |

## Algorithm

1. Resolver spec, slug, plan y state.
2. Calcular:
   - `spec_approval_status_payload`;
   - `plan_approval_status_payload`;
   - `policy_check_payload` para `plan`, `slice-start`, `workflow-run` y `release`.
3. Buscar reportes `.json` y `.md` cuyo nombre contenga el slug bajo `.flow/reports/**`.
4. Detectar si existe `ci spec` pasado.
5. Construir `missing`:
   - `spec_approval`;
   - `plan_approval`;
   - `release_policy`;
   - `ci_spec_passed`;
   - `reports`.
6. `ready_for_release=true` solo si no falta nada de lo anterior.
7. `bundle` copia reportes encontrados a `.flow/reports/evidence/<slug>/` y escribe JSON/Markdown de resumen.

## JSON Contract

```json
{
  "feature": "slug",
  "generated_at": "2026-04-16T00:00:00Z",
  "spec_path": "specs/features/slug.spec.md",
  "plan_path": ".flow/plans/slug.json",
  "ready_for_release": false,
  "missing": ["plan_approval"],
  "spec_approval": {},
  "plan_approval": {},
  "policies": {},
  "reports": [],
  "ci_spec": {
    "passed": false,
    "reports": []
  },
  "workflow": {
    "statuses": [],
    "reports": []
  }
}
```

## Stop Conditions

- Si spec approval esta stale, `ready_for_release=false`.
- Si plan approval esta stale, `ready_for_release=false`.
- Si policy release bloquea, `ready_for_release=false`.
- Si no hay reportes de CI spec pasado, `ready_for_release=false`.
- Bundle no debe fallar por reportes corruptos; debe omitir metadatos no parseables.

## Slice Breakdown

```yaml
- name: evidence-bundle-status
  targets:
    - ../../flow
    - ../../flowctl/parser.py
    - ../../flowctl/evidence.py
    - ../../flowctl/test_evidence.py
    - ../../README.md
    - ../../docs/softos-agent-dev-handbook.md
    - ../../specs/features/softos-evidence-bundle-status.spec.md
  hot_area: evidence reporting
  depends_on: []
  slice_mode: governance
  surface_policy: required
  minimum_valid_completion: evidence status and bundle consolidate approvals, policy and reports without mutating source-of-truth state
  validated_noop_allowed: false
  acceptable_evidence:
    - python3 -m unittest flowctl.test_evidence
    - python3 ./flow ci spec specs/features/softos-evidence-bundle-status.spec.md
```

## Verification Matrix

```yaml
- name: evidence-unit
  level: custom
  command: python3 -m unittest flowctl.test_evidence
  blocking_on:
    - ci
  environments:
    - local
  notes: valida missing evidence y copia de reportes al bundle

- name: spec-ci-evidence
  level: custom
  command: python3 ./flow ci spec specs/features/softos-evidence-bundle-status.spec.md
  blocking_on:
    - approval
  environments:
    - local
  notes: valida targets y estructura de spec
```

## Acceptance Criteria

- `flow evidence status <spec> --json` devuelve `ready_for_release`, `missing`, approvals, policies y reportes.
- `flow evidence bundle <spec> --json` escribe JSON/Markdown bajo `.flow/reports/evidence/`.
- El bundle copia reportes existentes de la spec.
- La salida bloqueada usa exit code `2`.
- Evidence no cambia frontmatter ni approvals.
