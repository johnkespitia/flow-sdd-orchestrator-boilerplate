# Workflow Stage Engine Contract

Spanish mirror: [docs/es/workflow-stage-engine-contract.es.md](./es/workflow-stage-engine-contract.es.md)

Source: `docs/workflow-stage-engine-contract.md`  
Last updated: 2026-05-07

## Stage order

`plan -> slice_start -> ci_spec -> ci_repo -> ci_integration -> release_promote -> release_verify -> infra_apply`

## Persisted stage record

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

## Operational controls

- Pause at stage:
  - `python3 ./flow workflow pause <slug> --stage <stage> --json`
  - `python3 ./flow workflow run <slug> --pause-at-stage <stage> --json`
- Resume:
  - `python3 ./flow workflow resume <slug> --stage <stage> --json`
  - `python3 ./flow workflow run <slug> --resume-from-stage <stage> --json`
- Retry:
  - `python3 ./flow workflow retry <slug> --stage <stage> --json`
  - `python3 ./flow workflow run <slug> --retry-stage <stage> --json`

## Idempotency rules

- If a stage is already `passed`, future runs mark it `skipped` unless explicitly retried.
- Retry increments `attempt` for the selected stage and continues execution.
- Failed stages stop the engine and preserve deterministic `failure_reason`.

## Gateway callbacks

If `SOFTOS_GATEWAY_WORKFLOW_CALLBACK_URL` is configured, the engine emits:

- `stage_started`
- `stage_passed`
- `stage_failed`
- `finalized`

## Multiagent scheduler

- During `slice_start`, the engine can run concurrent workers with queue controls.
- Scheduler report files:
  - `.flow/reports/workflows/<slug>-scheduler.json`
  - `.flow/reports/workflows/<slug>-scheduler.md`
- Report includes queue size, capacity limits, wait reasons, semantic locks, DLQ and traceability (`spec -> slice -> worker -> result`).

## Quality gates

- `workflow run` includes additive fields:
  - `quality_checkpoints`: result by checkpoint (required/status/reason)
  - `quality`: aggregated risk, thresholds, slice scores, and matrix `spec->slice->commit->test->release`
- Required checkpoints depend on stage + risk (`low|medium|high|critical`) and block progression when failing.
- API/DTO enforcement:
  - if there are `api/dto/contract/schema` changes, `ci_spec` requires:
    - `spec generate-contracts`
    - `contract verify`
  - failure reason is audited as `checkpoint-failed:<checkpoint>:<reason>`.
