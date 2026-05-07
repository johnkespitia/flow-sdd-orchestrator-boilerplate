# Contrato del workflow stage engine

English source: [docs/workflow-stage-engine-contract.md](../workflow-stage-engine-contract.md)

Source: `docs/workflow-stage-engine-contract.md`  
Last updated: 2026-05-07

## Orden de etapas

`plan -> slice_start -> ci_spec -> ci_repo -> ci_integration -> release_promote -> release_verify -> infra_apply`

## Registro persistido por etapa

Cada etapa persiste:

- `stage_name`
- `started_at`
- `finished_at`
- `status` (`started|passed|failed|skipped`)
- `input_ref`
- `output_ref`
- `attempt`
- `failure_reason`

El estado vive en `.flow/state/<slug>.json` bajo `workflow_engine`.

## Controles operativos

- Pausar en etapa:
  - `python3 ./flow workflow pause <slug> --stage <stage> --json`
  - `python3 ./flow workflow run <slug> --pause-at-stage <stage> --json`
- Reanudar:
  - `python3 ./flow workflow resume <slug> --stage <stage> --json`
  - `python3 ./flow workflow run <slug> --resume-from-stage <stage> --json`
- Reintentar:
  - `python3 ./flow workflow retry <slug> --stage <stage> --json`
  - `python3 ./flow workflow run <slug> --retry-stage <stage> --json`

## Reglas de idempotencia

- Si una etapa ya esta en `passed`, corridas futuras la marcan `skipped` salvo reintento explicito.
- El reintento incrementa `attempt` para la etapa seleccionada y continua ejecucion.
- Etapas fallidas detienen el engine y preservan `failure_reason` deterministico.

## Callbacks al gateway

Si `SOFTOS_GATEWAY_WORKFLOW_CALLBACK_URL` esta configurada, el engine emite:

- `stage_started`
- `stage_passed`
- `stage_failed`
- `finalized`

## Scheduler multiagente

- Durante `slice_start`, el engine puede correr workers concurrentes con controles de cola.
- Archivos de reporte del scheduler:
  - `.flow/reports/workflows/<slug>-scheduler.json`
  - `.flow/reports/workflows/<slug>-scheduler.md`
- El reporte incluye tamano de cola, limites de capacidad, razones de espera, locks semanticos, DLQ y trazabilidad (`spec -> slice -> worker -> resultado`).

## Quality gates

- `workflow run` incluye campos aditivos:
  - `quality_checkpoints`: resultado por checkpoint (required/status/reason)
  - `quality`: riesgo agregado, umbrales, scores por slice y matriz `spec->slice->commit->test->release`
- Los checkpoints requeridos dependen de etapa + riesgo (`low|medium|high|critical`) y bloquean avance cuando fallan.
- Enforcement API/DTO:
  - si hay cambios `api/dto/contract/schema`, `ci_spec` exige:
    - `spec generate-contracts`
    - `contract verify`
  - el motivo de fallo se audita como `checkpoint-failed:<checkpoint>:<reason>`.
