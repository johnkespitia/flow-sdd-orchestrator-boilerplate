---
schema_version: 3
name: "SoftOS central policy check"
description: "Agregar un policy check central y binario para stages sensibles, consumiendo approval gates formales de spec y plan."
status: approved
owner: platform
single_slice_reason: "the central policy command and first sensitive command integration are one bounded governance surface"
multi_domain: false
phases: []
depends_on:
  - specs/000-foundation/spec-as-source-operating-model.spec.md
  - specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - specs/features/softos-spec-approval-formal-gate.spec.md
  - specs/features/softos-plan-approval-formal-gate.spec.md
required_runtimes: []
required_services: []
required_capabilities: []
stack_projects: []
stack_services: []
stack_capabilities: []
targets:
  - ../../flow
  - ../../flowctl/parser.py
  - ../../flowctl/features.py
  - ../../flowctl/policy.py
  - ../../flowctl/test_policy_check.py
  - ../../flowctl/test_slice_governance.py
  - ../../README.md
  - ../../docs/softos-agent-dev-handbook.md
  - ../../specs/features/softos-central-policy-check.spec.md
---

# SoftOS central policy check

## Objetivo

Crear un policy check central para que humanos, agentes y runners puedan decidir de forma binaria si un spec puede entrar a un stage sensible:

- `flow policy check <spec> --stage plan --json`
- `flow policy check <spec> --stage slice-start --json`
- `flow policy check <spec> --stage workflow-run --json`
- `flow policy check <spec> --stage release --json`

## Contexto actual

- `v0.9.7` formalizo el gate de aprobacion de spec con hash.
- `v0.9.8` formalizo el gate de aprobacion de plan con hash y bloqueo de `slice start`.
- Sin esta spec, cada comando sensible tendria que decidir por su cuenta que gates consultar.

## Governing Decision

- El policy check no crea approvals y no modifica estado.
- El policy check consume los status payloads existentes de spec approval y plan approval.
- El resultado es binario: `allowed=true` devuelve exit code `0`; `allowed=false` devuelve exit code `2`.
- `slice start` debe usar el policy central cuando se invoca desde el wrapper principal `flow`.
- `workflow-run` y `release` quedan evaluables por policy, pero su integracion hard-block se implementa en olas posteriores.

## Executable Surface Inventory

| Superficie | Cambio obligatorio | Prohibido |
|---|---|---|
| `flowctl/policy.py` | Agregar stages, payload binario y comando `policy check`. | Duplicar hashing manual fuera de status payloads existentes. |
| `flowctl/parser.py` | Agregar `flow policy check`. | Cambiar contratos existentes de `spec approval-status` o `plan-approval-status`. |
| `flow` | Registrar wrapper de policy e inyectarlo en `slice start`. | Crear dependencia circular entre `features.py` y `policy.py`. |
| `flowctl/features.py` | Permitir que `slice start` use un policy checker inyectado. | Relajar el bloqueo existente de plan approval. |
| Tests | Cubrir allowed, blocked y exit code binario. | Depender de `.flow` real del repo. |
| Docs | Mostrar el policy check en el flujo de agente. | Prometer enforcement total de workflow/release antes de sus specs. |

## Algorithm

1. Normalizar `stage` a uno de:
   - `plan`
   - `slice-start`
   - `workflow-run`
   - `release`
2. Resolver spec y slug.
3. Calcular `spec_approval_status_payload`.
4. Calcular `plan_approval_status_payload`.
5. Aplicar matriz:
   - `plan`: requiere `spec_approval`.
   - `slice-start`: requiere `spec_approval` y `plan_approval`.
   - `workflow-run`: requiere `spec_approval` y `plan_approval`.
   - `release`: requiere `spec_approval` y `plan_approval`.
6. Construir `blocked_reasons` con formato `<gate>:<reason>`.
7. Construir `next_required_actions` sin duplicados.
8. Retornar exit code `0` si `allowed=true`, o `2` si `allowed=false`.

## JSON Contract

```json
{
  "feature": "slug",
  "spec_path": "specs/features/slug.spec.md",
  "plan_path": ".flow/plans/slug.json",
  "stage": "slice-start",
  "allowed": false,
  "checks": [
    {
      "name": "spec_approval",
      "required": true,
      "passed": false,
      "blocking": true,
      "invalid_reasons": ["missing_approval"],
      "next_required_action": "python3 ./flow spec approve slug"
    }
  ],
  "blocked_reasons": ["spec_approval:missing_approval"],
  "next_required_actions": ["python3 ./flow spec approve slug"]
}
```

## Stop Conditions

- Stage desconocido falla antes de evaluar gates.
- Missing spec approval bloquea `plan`, `slice-start`, `workflow-run` y `release`.
- Missing plan approval bloquea `slice-start`, `workflow-run` y `release`.
- `slice start` debe detenerse antes de crear worktree si el policy central lo bloquea.

## Slice Breakdown

```yaml
- name: central-policy-check
  targets:
    - ../../flow
    - ../../flowctl/parser.py
    - ../../flowctl/features.py
    - ../../flowctl/policy.py
    - ../../flowctl/test_policy_check.py
    - ../../flowctl/test_slice_governance.py
    - ../../README.md
    - ../../docs/softos-agent-dev-handbook.md
    - ../../specs/features/softos-central-policy-check.spec.md
  hot_area: policy gate governance
  depends_on: []
  slice_mode: governance
  surface_policy: required
  minimum_valid_completion: sensitive stages have a central binary policy check and slice-start consumes it
  validated_noop_allowed: false
  acceptable_evidence:
    - python3 -m unittest flowctl.test_policy_check
    - python3 -m pytest -q flowctl/test_slice_governance.py
    - python3 ./flow ci spec specs/features/softos-central-policy-check.spec.md
```

## Verification Matrix

```yaml
- name: policy-check-unit
  level: custom
  command: python3 -m unittest flowctl.test_policy_check
  blocking_on:
    - ci
  environments:
    - local
  notes: valida allowed, blocked y exit code 2 para policy denegado

- name: slice-policy-regression
  level: custom
  command: python3 -m pytest -q flowctl/test_slice_governance.py
  blocking_on:
    - ci
  environments:
    - local
  notes: valida que slice start sigue bloqueando antes de crear worktree

- name: spec-ci-policy-check
  level: custom
  command: python3 ./flow ci spec specs/features/softos-central-policy-check.spec.md
  blocking_on:
    - approval
  environments:
    - local
  notes: valida targets y estructura de spec
```

## Acceptance Criteria

- `flow policy check <spec> --stage plan --json` bloquea si la spec no esta aprobada por hash.
- `flow policy check <spec> --stage slice-start --json` bloquea si falta aprobacion vigente de spec o plan.
- El JSON incluye `allowed`, `checks`, `blocked_reasons` y `next_required_actions`.
- Un policy bloqueado retorna exit code `2`.
- `flow slice start` desde el wrapper principal usa el policy central inyectado.
