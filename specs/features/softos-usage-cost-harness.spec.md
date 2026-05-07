---
schema_version: 3
name: "SoftOS usage and cost harness"
description: "Agregar telemetria de uso/costo para checkpoints de agentes, estimaciones, reconciliacion de proveedor y reportes de closeout."
status: approved
owner: platform
single_slice_reason: "usage/cost harness is a bounded governance and reporting layer over existing Harness Core profiles"
multi_domain: false
phases: []
depends_on:
  - specs/000-foundation/spec-as-source-operating-model.spec.md
  - specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
required_runtimes: []
required_services: []
required_capabilities: []
stack_projects: []
stack_services: []
stack_capabilities: []
targets:
  - ../../workspace.config.json
  - ../../policies/harness-core/README.md
  - ../../policies/harness-core/usage-and-cost.md
  - ../../profiles/README.md
  - ../../profiles/es/README.es.md
  - ../../profiles/example-api-ticket/README.md
  - ../../profiles/example-api-ticket/README.es.md
  - ../../profiles/example-api-ticket/profile.json
  - ../../scripts/harness/validate_profile.py
  - ../../scripts/harness/usage_report.py
  - ../../docs/harness-core-and-profiles.md
  - ../../docs/es/harness-core-and-profiles.es.md
  - ../../specs/features/softos-usage-cost-harness.spec.md
---

# SoftOS Usage and Cost Harness

## Objetivo

Agregar un Harness reusable de uso/costo para que SoftOS pueda reportar consumo
de modelos, herramientas y automatizaciones durante progress updates y closeout.

## Contexto actual

- Harness Core ya define gates, evidencia, hipercomunicacion y PR readiness.
- Los workflows largos pueden consumir tokens, llamadas de herramientas, sesiones
  de runtime y otros recursos billables sin visibilidad incremental.
- Algunas ejecuciones exponen uso exacto por request, otras solo pueden
  reconciliarse por proveedor, y otras requieren estimacion local.

## Governing Decision

- Todo valor de uso/costo debe declarar un modo: `exact`,
  `provider_reconciled` o `estimated`.
- El costo reconciliado por proveedor es la fuente financiera de verdad cuando
  existe, pero puede tener lag y puede no mapear perfecto a un ticket salvo que
  se aisle por proyecto, API key, usuario o ventana.
- El helper no guarda credenciales, prompts crudos, transcripts privados ni
  datos sensibles.
- El budget gate es reportable por defecto y solo bloqueante cuando el profile u
  operador define umbrales.

## Executable Surface Inventory

| Superficie | Cambio obligatorio | Prohibido |
|---|---|---|
| `policies/harness-core/usage-and-cost.md` | Definir signal classes, checkpoints, budget gates, final report y privacidad. | Mencionar repos, tickets o canales privados. |
| `profiles/example-api-ticket/profile.json` | Declarar `usage_telemetry` reusable y open-source-safe. | Asumir un proveedor obligatorio. |
| `scripts/harness/usage_report.py` | Crear checkpoints, summaries y snapshot opcional de proveedor sin dependencias externas. | Guardar credenciales o requerir red para el modo local. |
| `scripts/harness/validate_profile.py` | Exigir estructura minima de `usage_telemetry`. | Codificar reglas de una organizacion privada. |
| Docs/i18n | Documentar adopcion y comandos. | Prometer exactitud cuando el runtime no la expone. |

## Algorithm

1. Un profile activa `usage_telemetry.enabled=true` y define triggers, fields,
   budget, evidence paths y reconciliacion.
2. Durante el proceso, el agente u operador ejecuta `usage_report.py checkpoint`
   con los datos disponibles y el modo correcto.
3. En progress updates largos se copia el bloque `Usage update` generado.
4. Al cierre, `usage_report.py summary` genera el reporte Markdown.
5. Si hay credenciales admin y una ventana apropiada, `openai-snapshot` puede
   agregar un checkpoint `provider_reconciled` sin guardar credenciales.

## Stop Conditions

- Un profile sin `usage_telemetry` no pasa `validate_profile.py`.
- Un checkpoint sin modo valido debe fallar.
- Un reporte no debe guardar credenciales, prompts crudos ni datos sensibles.
- Si se alcanza el umbral de pausa de budget, el profile debe pedir aprobacion
  antes de continuar.

## Slice Breakdown

```yaml
- name: usage-cost-harness
  targets:
    - ../../workspace.config.json
    - ../../policies/harness-core/README.md
    - ../../policies/harness-core/usage-and-cost.md
    - ../../profiles/README.md
    - ../../profiles/es/README.es.md
    - ../../profiles/example-api-ticket/README.md
    - ../../profiles/example-api-ticket/README.es.md
    - ../../profiles/example-api-ticket/profile.json
    - ../../scripts/harness/validate_profile.py
    - ../../scripts/harness/usage_report.py
    - ../../docs/harness-core-and-profiles.md
    - ../../docs/es/harness-core-and-profiles.es.md
    - ../../specs/features/softos-usage-cost-harness.spec.md
  hot_area: harness governance and usage reporting
  depends_on: []
  slice_mode: governance
  surface_policy: required
  minimum_valid_completion: usage telemetry validates, checkpoint smoke works, and docs are mirrored
  validated_noop_allowed: false
  acceptable_evidence:
    - validate_profile JSON status ok
    - py_compile for validator and usage_report
    - docs i18n validation passed
    - usage_report checkpoint and summary smoke output
```

## Validation Plan

- Run `python3 scripts/harness/validate_profile.py --root . --json`.
- Run `python3 -m py_compile scripts/harness/validate_profile.py scripts/harness/usage_report.py`.
- Run `python3 scripts/ci/validate_docs_i18n.py`.
- Run a local smoke checkpoint and summary using `scripts/harness/usage_report.py` with `/private/tmp` outputs.
- Confirm the new core/example/docs files do not contain project-private links,
  credentials, or organization-specific commands.

## Open Questions

None
