---
schema_version: 3
name: "SoftOS human-gated workflow runner"
description: "Agregar modo human-gated al workflow runner para pausar ejecucion autonoma cuando el policy central requiere aprobacion humana."
status: approved
owner: platform
single_slice_reason: "human-gated workflow mode is one bounded runner behavior using existing policy and pause state"
multi_domain: false
phases: []
depends_on:
  - specs/000-foundation/spec-as-source-operating-model.spec.md
  - specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - specs/features/softos-spec-approval-formal-gate.spec.md
  - specs/features/softos-plan-approval-formal-gate.spec.md
  - specs/features/softos-central-policy-check.spec.md
required_runtimes: []
required_services: []
required_capabilities: []
stack_projects: []
stack_services: []
stack_capabilities: []
targets:
  - ../../flow
  - ../../flowctl/parser.py
  - ../../flowctl/workflows.py
  - ../../flowctl/test_workflow_engine.py
  - ../../README.md
  - ../../docs/softos-agent-dev-handbook.md
  - ../../specs/features/softos-human-gated-workflow-runner.spec.md
---

# SoftOS human-gated workflow runner

## Objetivo

Permitir que `flow workflow run <spec> --human-gated --json` ejecute el SDLC autonomo hasta el siguiente punto donde haga falta aprobacion humana formal.

## Contexto actual

- `v0.9.7` agrego aprobacion formal de spec con hash.
- `v0.9.8` agrego aprobacion formal de plan con hash.
- `v0.9.9` agrego `flow policy check` como decision binaria central.
- Antes de esta spec, `workflow run` podia pausarse manualmente con `--pause-at-stage`, pero no pausaba automaticamente por gates humanos.

## Governing Decision

- El workflow runner no reimplementa approvals.
- `--human-gated` consulta el policy central antes de stages sensibles.
- Si policy bloquea, el runner no falla: pausa y registra el gate pendiente.
- El humano desbloquea aprobando spec/plan y luego usa resume.
- El modo default sin `--human-gated` conserva el comportamiento existente.

## Executable Surface Inventory

| Superficie | Cambio obligatorio | Prohibido |
|---|---|---|
| `flowctl/parser.py` | Agregar `workflow run --human-gated`. | Cambiar semantica de `--pause-at-stage`, `--resume-from-stage` o `--retry-stage`. |
| `flowctl/workflows.py` | Antes de stages sensibles, consultar policy inyectado y pausar si `allowed=false`. | Crear un segundo sistema de approvals dentro del engine. |
| `flow` | Inyectar `flow_policy.policy_check_payload` en el runner. | Duplicar reglas de policy en el wrapper. |
| Tests | Cubrir pausa por human gate y resume tras approval. | Depender de `.flow` real del repo. |
| Docs | Mostrar el uso recomendado de `--human-gated`. | Prometer cierre production completo antes de evidence/scope releases. |

## Algorithm

1. Resolver spec y slug.
2. Si `--human-gated` esta activo, evaluar policy antes de stages sensibles:
   - `plan` -> stage policy `plan`;
   - `slice_start` -> stage policy `slice-start`;
   - `release_promote` -> stage policy `release`;
   - `release_verify` -> stage policy `release`.
3. Si `policy.allowed=true`, ejecutar el stage normal.
4. Si `policy.allowed=false`:
   - marcar el record del stage como `blocked`;
   - guardar `failure_reason=human-gate-blocked`;
   - guardar el payload `human_gate`;
   - marcar `workflow_engine.status=paused`;
   - marcar `workflow_engine.paused_at_stage=<stage>`;
   - retornar payload final con `status=paused`.
5. En resume, volver a evaluar policy; si el humano ya aprobo, continuar.

## JSON Contract

Cuando el gate bloquea:

```json
{
  "status": "paused",
  "engine_status": "paused",
  "stages": [
    {
      "stage_name": "plan",
      "status": "blocked",
      "failure_reason": "human-gate-blocked",
      "human_gate": {
        "allowed": false,
        "blocked_reasons": ["spec_approval:missing_approval"],
        "next_required_actions": ["python3 ./flow spec approve slug"]
      }
    }
  ]
}
```

## Stop Conditions

- Si `policy_check_callable` no esta inyectado, `--human-gated` no debe romper el modo existente.
- Si policy bloquea, no se ejecuta el callable del stage.
- Si resume encuentra policy aprobado, el runner continua desde el stage indicado.
- Un pause por human gate no debe crear DLQ ni rollback como si fuera fallo tecnico.

## Slice Breakdown

```yaml
- name: human-gated-workflow-runner
  targets:
    - ../../flow
    - ../../flowctl/parser.py
    - ../../flowctl/workflows.py
    - ../../flowctl/test_workflow_engine.py
    - ../../README.md
    - ../../docs/softos-agent-dev-handbook.md
    - ../../specs/features/softos-human-gated-workflow-runner.spec.md
  hot_area: workflow engine gating
  depends_on: []
  slice_mode: governance
  surface_policy: required
  minimum_valid_completion: workflow runner pauses instead of failing when human approval gates block execution
  validated_noop_allowed: false
  acceptable_evidence:
    - python3 -m unittest flowctl.test_workflow_engine
    - python3 ./flow ci spec specs/features/softos-human-gated-workflow-runner.spec.md
```

## Verification Matrix

```yaml
- name: workflow-engine-human-gated-unit
  level: custom
  command: python3 -m unittest flowctl.test_workflow_engine
  blocking_on:
    - ci
  environments:
    - local
  notes: valida pausa por policy y resume tras aprobacion

- name: spec-ci-human-gated-runner
  level: custom
  command: python3 ./flow ci spec specs/features/softos-human-gated-workflow-runner.spec.md
  blocking_on:
    - approval
  environments:
    - local
  notes: valida targets y estructura de spec
```

## Acceptance Criteria

- `flow workflow run <spec> --human-gated --json` acepta el flag.
- Si policy bloquea `plan`, el runner retorna `status=paused`.
- El estado persistido incluye `workflow_engine.human_gate`.
- El stage bloqueado incluye `status=blocked` y `failure_reason=human-gate-blocked`.
- Resume puede continuar cuando policy permite el stage.
