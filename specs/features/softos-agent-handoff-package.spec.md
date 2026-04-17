---
schema_version: 3
name: "SoftOS agent handoff package"
description: "Agregar un paquete de handoff para que otro agente retome una spec con plan, evidence, policy, slices y comandos recomendados sin depender del chat."
status: approved
owner: platform
single_slice_reason: "agent handoff packaging is one bounded reporting surface layered on evidence bundles"
multi_domain: false
phases: []
depends_on:
  - specs/000-foundation/spec-as-source-operating-model.spec.md
  - specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - specs/features/softos-spec-approval-formal-gate.spec.md
  - specs/features/softos-plan-approval-formal-gate.spec.md
  - specs/features/softos-central-policy-check.spec.md
  - specs/features/softos-human-gated-workflow-runner.spec.md
  - specs/features/softos-evidence-bundle-status.spec.md
required_runtimes: []
required_services: []
required_capabilities: []
stack_projects: []
stack_services: []
stack_capabilities: []
targets:
  - ../../flow
  - ../../flowctl/parser.py
  - ../../flowctl/agent_handoff.py
  - ../../flowctl/test_agent_handoff.py
  - ../../README.md
  - ../../docs/softos-agent-dev-handbook.md
  - ../../specs/features/softos-agent-handoff-package.spec.md
---

# SoftOS agent handoff package

## Objetivo

Agregar `flow agent handoff <spec> --json` para producir un paquete autocontenido que otro agente pueda usar como entrada operacional.

El paquete debe incluir:

- spec y plan como fuente de verdad;
- evidence bundle vigente;
- policy y blockers;
- slices, targets, comandos y closeout contract;
- JSON/Markdown bajo `.flow/reports/agent-handoffs/`;
- copias de artefactos clave en `.flow/reports/agent-handoffs/<slug>/`.

## Contexto actual

- `v0.10.1` agrego `flow evidence status|bundle`.
- `workflow execute-feature` ya puede generar handoffs por slice, pero depende de materializar slices y no resume todo el estado de approvals/policy/evidence.
- Para transferir trabajo entre agentes se necesita un paquete unico que no dependa del contexto conversacional.

## Governing Decision

- Agent handoff no ejecuta implementacion.
- Agent handoff no reemplaza approvals, policy ni evidence.
- Agent handoff llama las mismas funciones de evidence para mantener una sola lectura de readiness.
- Si la evidencia no esta lista, el comando escribe paquete igualmente pero sale con codigo `2`.
- El paquete declara blockers y next commands en vez de asumir que el receptor puede ejecutar.

## Executable Surface Inventory

| Superficie | Cambio obligatorio | Prohibido |
|---|---|---|
| `flowctl/agent_handoff.py` | Agregar payload, escritura JSON/Markdown y copia de inputs/evidence. | Crear un segundo scanner de CI/policy distinto a evidence. |
| `flowctl/parser.py` | Agregar `flow agent handoff`. | Cambiar `workflow execute-feature`. |
| `flow` | Registrar wrappers y directorio `.flow/reports/agent-handoffs`. | Ejecutar slices o worktrees desde handoff. |
| Tests | Cubrir paquete listo y paquete bloqueado. | Depender de `.flow` real del repo. |
| Docs | Mostrar comando en flujo recomendado. | Prometer que handoff equivale a release readiness final. |

## Algorithm

1. Resolver spec, slug, plan y state.
2. Calcular evidence status con `evidence_status_payload`.
3. Escribir evidence bundle con `write_evidence_bundle`.
4. Leer plan JSON si existe.
5. Copiar spec y plan a `.flow/reports/agent-handoffs/<slug>/`.
6. Copiar reportes del evidence bundle a `.flow/reports/agent-handoffs/<slug>/evidence/`.
7. Construir:
   - `ready_for_agent`;
   - `blocked_actions`;
   - `next_commands`;
   - `execution_contract`;
   - `slices`;
   - `copied_inputs`.
8. Escribir:
   - `.flow/reports/agent-handoffs/<slug>-agent-handoff.json`;
   - `.flow/reports/agent-handoffs/<slug>-agent-handoff.md`.
9. Retornar `0` si `ready_for_agent=true`, o `2` si hay blockers.

## JSON Contract

```json
{
  "feature": "slug",
  "generated_at": "2026-04-17T00:00:00Z",
  "spec_path": "specs/features/slug.spec.md",
  "plan_path": ".flow/plans/slug.json",
  "handoff_root": ".flow/reports/agent-handoffs/slug",
  "ready_for_agent": false,
  "blocked_actions": ["plan_approval"],
  "next_commands": ["python3 ./flow plan-approve slug --approver <human>"],
  "execution_contract": {
    "source_of_truth": "specs/features/slug.spec.md",
    "plan": ".flow/plans/slug.json",
    "evidence_bundle": {},
    "policy_release_allowed": false
  },
  "slices": [],
  "evidence": {},
  "copied_inputs": []
}
```

## Stop Conditions

- Missing spec approval must appear as blocker.
- Missing plan approval must appear as blocker.
- Missing CI/evidence must appear as blocker.
- Handoff must not create worktrees or run implementation commands.
- Handoff must still write artifacts when blockers exist.

## Slice Breakdown

```yaml
- name: agent-handoff-package
  targets:
    - ../../flow
    - ../../flowctl/parser.py
    - ../../flowctl/agent_handoff.py
    - ../../flowctl/test_agent_handoff.py
    - ../../README.md
    - ../../docs/softos-agent-dev-handbook.md
    - ../../specs/features/softos-agent-handoff-package.spec.md
  hot_area: agent handoff reporting
  depends_on: []
  slice_mode: governance
  surface_policy: required
  minimum_valid_completion: agent handoff packages spec, plan, evidence, policy and next commands without executing implementation
  validated_noop_allowed: false
  acceptable_evidence:
    - python3 -m unittest flowctl.test_agent_handoff
    - python3 ./flow ci spec specs/features/softos-agent-handoff-package.spec.md
```

## Verification Matrix

```yaml
- name: agent-handoff-unit
  level: custom
  command: python3 -m unittest flowctl.test_agent_handoff
  blocking_on:
    - ci
  environments:
    - local
  notes: valida paquete listo, blockers y copias de inputs

- name: spec-ci-agent-handoff
  level: custom
  command: python3 ./flow ci spec specs/features/softos-agent-handoff-package.spec.md
  blocking_on:
    - approval
  environments:
    - local
  notes: valida targets y estructura de spec
```

## Acceptance Criteria

- `flow agent handoff <spec> --json` escribe JSON/Markdown.
- El paquete incluye spec, plan, evidence, policy y slices.
- El paquete copia spec/plan/reportes a `.flow/reports/agent-handoffs/<slug>/`.
- Si hay blockers, el comando retorna exit code `2`.
- Si no hay blockers, retorna `0` y `ready_for_agent=true`.
