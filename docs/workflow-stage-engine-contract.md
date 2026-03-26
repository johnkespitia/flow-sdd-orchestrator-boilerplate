# Workflow Stage Engine Contract

## Stage Order

`plan -> slice_start -> ci_spec -> ci_repo -> ci_integration -> release_promote -> release_verify -> infra_apply`

## Persisted Stage Record

Each stage persists:

- `stage_name`
- `started_at`
- `finished_at`
- `status` (`started|passed|failed|skipped`)
- `input_ref`
- `output_ref`
- `attempt`
- `failure_reason`

State lives in `.flow/state/<slug>.json` under `workflow_engine`.

## Operational Controls

- Pause at stage:
  - `python3 ./flow workflow pause <slug> --stage <stage> --json`
  - `python3 ./flow workflow run <slug> --pause-at-stage <stage> --json`
- Resume:
  - `python3 ./flow workflow resume <slug> --stage <stage> --json`
  - `python3 ./flow workflow run <slug> --resume-from-stage <stage> --json`
- Retry:
  - `python3 ./flow workflow retry <slug> --stage <stage> --json`
  - `python3 ./flow workflow run <slug> --retry-stage <stage> --json`

## Idempotency Rules

- If a stage is already `passed`, future runs mark it `skipped` unless explicitly retried.
- Retry increments `attempt` for the selected stage and continues execution.
- Failed stages stop the engine and preserve deterministic `failure_reason`.

## Gateway Callbacks

If `SOFTOS_GATEWAY_WORKFLOW_CALLBACK_URL` is configured, the engine emits:

- `stage_started`
- `stage_passed`
- `stage_failed`
- `finalized`

## Multiagent Scheduler

- During `slice_start`, the engine can run concurrent workers with queue controls.
- Scheduler report files:
  - `.flow/reports/workflows/<slug>-scheduler.json`
  - `.flow/reports/workflows/<slug>-scheduler.md`
- Report includes queue size, capacity limits, wait reasons, semantic locks, DLQ and traceability (`spec -> slice -> worker -> resultado`).

## Quality Gates

- `workflow run` now includes additive fields:
  - `quality_checkpoints`: resultado por checkpoint (required/status/reason)
  - `quality`: riesgo agregado, umbrales, scores por slice y matriz `spec->slice->commit->test->release`
- Checkpoints requeridos dependen de etapa + riesgo (`low|medium|high|critical`) y bloquean avance cuando fallan.
- Enforcement API/DTO:
  - si hay cambios `api/dto/contract/schema`, en `ci_spec` se exige:
    - `spec generate-contracts`
    - `contract verify`
  - failure reason queda auditado como `checkpoint-failed:<checkpoint>:<reason>`.
