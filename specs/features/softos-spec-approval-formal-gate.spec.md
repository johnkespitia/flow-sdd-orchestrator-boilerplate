---
schema_version: 3
name: "SoftOS spec approval formal gate"
description: "Formalizar la aprobacion humana de specs con hash de contenido aprobado, estado consultable e invalidacion detectable si la spec cambia despues de aprobarse."
status: approved
owner: platform
single_slice_reason: "spec approval hashing and status inspection are one bounded governance gate"
multi_domain: false
phases: []
depends_on:
  - specs/000-foundation/spec-as-source-operating-model.spec.md
  - specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - specs/features/softos-engram-autonomous-flow-hooks.spec.md
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
  - ../../flowctl/test_spec_approval_gate.py
  - ../../README.md
  - ../../docs/softos-agent-dev-handbook.md
  - ../../specs/features/softos-spec-approval-formal-gate.spec.md
---

# SoftOS spec approval formal gate

## Objetivo

Cerrar el gate formal de aprobacion humana de specs sin automatizar aprobacion de planes:

- `flow spec approve <spec> --approver <id>` persiste hash SHA-256 del contenido aprobado.
- `flow spec approval-status <spec> --json` expone una respuesta binaria reutilizable por agentes y policies.
- Si el contenido de la spec cambia despues de aprobarse, `approval-status` devuelve `approved=false`.
- El frontmatter `status: approved` se conserva como compatibilidad y lectura humana, pero el hash queda como evidencia operacional fuerte.

## Contexto actual

- `flow spec review` ya genera reportes y guarda `last_review` en `.flow/state/<slug>.json`.
- `flow spec approve` ya exige review previa lista para aprobar y cambia `status: approved`.
- Antes de esta spec, la aprobacion dependia de `mtime` y del frontmatter; eso no era suficiente como gate formal reutilizable.
- `v0.9.8` agregara aprobacion formal de planes; esta spec no debe adelantar ese comportamiento.

## Governing Decision

- La spec sigue siendo la fuente de verdad.
- `.flow/state/<slug>.json` guarda evidencia operacional de la decision humana.
- El hash aprobado se calcula despues de escribir `status: approved`, porque ese es el contenido final aprobado.
- `approval-status` nunca modifica estado; solo reporta si la aprobacion vigente coincide con el contenido actual.
- Esta ola no bloquea `slice start`, `workflow run` ni release por plan approval; esos gates se introducen en specs posteriores.

## Executable Surface Inventory

| Superficie | Cambio obligatorio | Prohibido |
|---|---|---|
| `flowctl/features.py` | Agregar hash SHA-256, metadata en `last_approval`, payload de `approval-status` y comando interno. | Cambiar semantica de aprobacion de plan. |
| `flowctl/parser.py` | Agregar `spec approval-status <spec> --json`. | Romper `spec approve`. |
| `flow` | Registrar `command_spec_approval_status`. | Saltar `flowctl/features.py` con logica duplicada. |
| `flowctl/test_spec_approval_gate.py` | Cubrir hash aprobado e invalidacion por cambio de contenido. | Usar estado real `.flow/**` en tests unitarios. |
| Docs | Documentar el nuevo gate en el flujo minimo/agente. | Prometer autonomia total. |

## Algorithm

1. `flow spec review <spec>` calcula `spec_hash` sobre el contenido revisado y lo guarda en `state.last_review.spec_hash`.
2. `flow spec approve <spec>` valida:
   - existe review previa;
   - `ready_to_approve=true`;
   - `state.last_review.spec_mtime_ns` coincide con el archivo actual;
   - si existe `state.last_review.spec_hash`, coincide con el hash actual.
3. `flow spec approve` ejecuta `replace_frontmatter_status(spec, "approved")`.
4. Despues de cambiar el frontmatter, calcula `last_approval.spec_hash` sobre el contenido aprobado final.
5. `flow spec approval-status <spec> --json` calcula hash actual y compara contra `state.last_approval.spec_hash`.
6. Si no hay approval o el hash no coincide, devuelve `approved=false` y `invalid_reasons`.

## JSON Contract

`flow spec approval-status <spec> --json` debe devolver al menos:

```json
{
  "feature": "slug",
  "spec_path": "specs/features/slug.spec.md",
  "approved": false,
  "approval": {},
  "current_spec_hash": "hex-sha256",
  "current_spec_mtime_ns": 123,
  "invalid_reasons": ["missing_approval"],
  "next_required_action": "python3 ./flow spec approve slug"
}
```

## Stop Conditions

- Si `approval-status` requiere inventar datos no presentes en estado, devolver `approved=false`.
- Si `spec approve` detecta cambio despues de review, fallar y pedir nueva review.
- Si una implementacion intenta usar esta spec para exigir plan approval, detenerse: eso pertenece a `v0.9.8`.

## Slice Breakdown

```yaml
- name: spec-approval-formal-gate
  targets:
    - ../../flow
    - ../../flowctl/parser.py
    - ../../flowctl/features.py
    - ../../flowctl/test_spec_approval_gate.py
    - ../../README.md
    - ../../docs/softos-agent-dev-handbook.md
    - ../../specs/features/softos-spec-approval-formal-gate.spec.md
  hot_area: spec approval governance
  depends_on: []
  slice_mode: governance
  surface_policy: required
  minimum_valid_completion: spec approval persists approved-content hash and approval-status reports stale approvals
  validated_noop_allowed: false
  acceptable_evidence:
    - python3 -m unittest flowctl.test_spec_approval_gate
    - python3 ./flow ci spec specs/features/softos-spec-approval-formal-gate.spec.md
    - python3 ./flow spec review specs/features/softos-spec-approval-formal-gate.spec.md
```

## Verification Matrix

```yaml
- name: spec-approval-unit
  level: custom
  command: python3 -m unittest flowctl.test_spec_approval_gate
  blocking_on:
    - ci
  environments:
    - local
  notes: valida hash de contenido aprobado e invalidacion por cambio posterior

- name: spec-ci-formal-approval
  level: custom
  command: python3 ./flow ci spec specs/features/softos-spec-approval-formal-gate.spec.md
  blocking_on:
    - approval
  environments:
    - local
  notes: valida targets y estructura de spec

- name: spec-review-formal-approval
  level: custom
  command: python3 ./flow spec review specs/features/softos-spec-approval-formal-gate.spec.md
  blocking_on:
    - review
  environments:
    - local
  notes: valida que la spec quede lista para aprobacion humana
```

## Acceptance Criteria

- `flow spec approve` guarda `last_approval.spec_hash`.
- El hash guardado corresponde al contenido final con `status: approved`.
- `flow spec approval-status --json` devuelve `approved=true` cuando el hash coincide.
- `approval-status` devuelve `approved=false` con `spec_hash_changed` cuando la spec cambia.
- La implementacion no introduce plan approval ni human-gated workflow behavior.
