---
schema_version: 3
name: "SoftOS plan approval formal gate"
description: "Agregar aprobacion humana formal de planes con hash de plan, hash de spec aprobada e invalidacion detectable antes de iniciar slices."
status: approved
owner: platform
single_slice_reason: "plan approval hashing and slice-start enforcement are one bounded governance gate"
multi_domain: false
phases: []
depends_on:
  - specs/000-foundation/spec-as-source-operating-model.spec.md
  - specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - specs/features/softos-spec-approval-formal-gate.spec.md
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
  - ../../flowctl/test_plan_approval_gate.py
  - ../../flowctl/test_slice_governance.py
  - ../../README.md
  - ../../docs/softos-agent-dev-handbook.md
  - ../../specs/features/softos-plan-approval-formal-gate.spec.md
---

# SoftOS plan approval formal gate

## Objetivo

Formalizar la aprobacion humana de planes generados por `flow plan`:

- `flow plan-approve <spec> --approver <id>` guarda hash del plan y hash vigente de la spec aprobada.
- `flow plan-approval-status <spec> --json` reporta si el plan sigue aprobado.
- Regenerar el plan invalida la aprobacion previa.
- `flow slice start` bloquea si el plan no tiene aprobacion vigente.

## Contexto actual

- `v0.9.7` agrego aprobacion formal de specs con hash.
- `flow plan <spec>` ya genera `.flow/plans/<slug>.json` y `.md`.
- Antes de esta spec, un actor podia iniciar slices solo con `frontmatter.status=approved`, sin aprobacion explicita del plan.

## Governing Decision

- El humano aprueba la spec primero y el plan despues.
- La aprobacion del plan referencia dos hashes: spec aprobada vigente y plan JSON vigente.
- `flow plan <spec>` sigue siendo compatible como comando top-level; por eso se agregan `plan-approve` y `plan-approval-status` como comandos separados.
- `slice start` es el primer comando sensible que exige plan approval vigente.
- `workflow human-gated` y `policy check` se implementan despues; esta ola solo crea el gate reusable y lo aplica a slices.

## Executable Surface Inventory

| Superficie | Cambio obligatorio | Prohibido |
|---|---|---|
| `flowctl/features.py` | Agregar payload/commands de plan approval, invalidar approval al regenerar plan, bloquear `slice start` sin approval vigente. | Auto-aprobar planes generados. |
| `flowctl/parser.py` | Agregar `plan-approve` y `plan-approval-status`. | Convertir `flow plan <spec>` en subcommand incompatible. |
| `flow` | Registrar wrappers de plan approval. | Duplicar logica de hashes fuera de `flowctl/features.py`. |
| Tests | Cubrir plan hash, invalidacion y compatibilidad de slice governance. | Depender de `.flow` real del repo. |
| Docs | Mostrar el gate en el flujo minimo y agente. | Prometer policy central antes de `v0.9.9`. |

## Algorithm

1. `flow plan <spec>` genera plan JSON/MD como antes.
2. Si el estado tenia `plan_approval`, el comando la mueve a `previous_plan_approval`, elimina `plan_approval` e informa invalidacion operacional con `plan_approval_invalidated_at`.
3. `flow plan-approve <spec>` valida:
   - existe `.flow/plans/<slug>.json`;
   - la spec tiene aprobacion vigente por hash;
   - existe identidad de approver.
4. `plan-approve` persiste `state.plan_approval` con:
   - `status=approved`;
   - `approver`;
   - `approved_at`;
   - `spec_hash`;
   - `plan_hash`;
   - `plan_json`.
5. `flow plan-approval-status <spec> --json` compara hashes actuales contra `state.plan_approval`.
6. `flow slice start <spec> <slice>` llama el mismo status payload y falla si `approved=false`.

## JSON Contract

```json
{
  "feature": "slug",
  "spec_path": "specs/features/slug.spec.md",
  "plan_path": ".flow/plans/slug.json",
  "approved": false,
  "approval": {},
  "current_spec_hash": "hex-sha256",
  "current_plan_hash": "hex-sha256",
  "invalid_reasons": ["missing_plan_approval"],
  "next_required_action": "python3 ./flow plan-approve slug"
}
```

## Stop Conditions

- Si no existe plan, `plan-approve` falla y pide `flow plan`.
- Si la spec approval esta stale, `plan-approve` falla y pide reaprobar spec.
- Si el plan cambia despues de aprobarse, `plan-approval-status` falla con `plan_hash_changed`.
- Si un comando intenta iniciar slices sin plan approval, debe detenerse antes de crear worktrees.

## Slice Breakdown

```yaml
- name: plan-approval-formal-gate
  targets:
    - ../../flow
    - ../../flowctl/parser.py
    - ../../flowctl/features.py
    - ../../flowctl/test_plan_approval_gate.py
    - ../../flowctl/test_slice_governance.py
    - ../../README.md
    - ../../docs/softos-agent-dev-handbook.md
    - ../../specs/features/softos-plan-approval-formal-gate.spec.md
  hot_area: plan approval governance
  depends_on: []
  slice_mode: governance
  surface_policy: required
  minimum_valid_completion: generated plans require explicit approval before slice start
  validated_noop_allowed: false
  acceptable_evidence:
    - python3 -m unittest flowctl.test_plan_approval_gate
    - python3 -m pytest -q flowctl/test_slice_governance.py
    - python3 ./flow ci spec specs/features/softos-plan-approval-formal-gate.spec.md
```

## Verification Matrix

```yaml
- name: plan-approval-unit
  level: custom
  command: python3 -m unittest flowctl.test_plan_approval_gate
  blocking_on:
    - ci
  environments:
    - local
  notes: valida plan hash e invalidacion por cambio de plan

- name: slice-governance-regression
  level: custom
  command: python3 -m pytest -q flowctl/test_slice_governance.py
  blocking_on:
    - ci
  environments:
    - local
  notes: valida que slice start conserva handoff y ahora usa plan approval vigente

- name: spec-ci-plan-approval
  level: custom
  command: python3 ./flow ci spec specs/features/softos-plan-approval-formal-gate.spec.md
  blocking_on:
    - approval
  environments:
    - local
  notes: valida targets y estructura
```

## Acceptance Criteria

- `plan-approve` guarda `state.plan_approval.plan_hash`.
- `plan-approval-status --json` detecta `plan_hash_changed`.
- `flow plan` invalida una aprobacion de plan anterior.
- `slice start` falla si no hay plan approval vigente.
- La CLI `flow plan <spec>` conserva compatibilidad.
