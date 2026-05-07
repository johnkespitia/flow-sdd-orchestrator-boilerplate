# Matriz de evidencia de cierre del programa

Spanish mirror: [docs/es/program-closure-evidence-matrix.es.md](./es/program-closure-evidence-matrix.es.md)

Source: `docs/program-closure-evidence-matrix.md`  
Last updated: 2026-05-06

Esta tabla fija la evidencia versionada de los ítems de cierre ya resueltos en `softos-program-closure-and-operational-readiness`.
La intención es que el artefacto sea consumible por humanos y verificable por CI, sin depender de estado efímero en `.flow/**`.

| Txx | archivo | test/comando | resultado |
| --- | --- | --- | --- |
| T01 | [`gateway/app/approval_policy.py`](../gateway/app/approval_policy.py) | `uv run python -m pytest -q gateway/tests/test_intents_ola_a.py -k t01` | `passed`; la política CLI vs gateway exige `approver` donde corresponde y publica intents permitidos. |
| T02 | [`gateway/app/intents.py`](../gateway/app/intents.py) | `uv run python -m pytest -q gateway/tests/test_intents_ola_a.py -k t02` | `passed`; GitHub/Jira soportan aprobación simple (`approve`, `/approve`, `review`). |
| T03 | [`gateway/tests/test_intents_ola_a.py`](../gateway/tests/test_intents_ola_a.py) | `uv run python -m pytest -q gateway/tests/test_intents_ola_a.py -k t03` | `passed`; la suite cubre `issues`, `issue_comment` y dedupe semántico. |
| T04 | [`gateway/tests/test_intents_ola_a.py`](../gateway/tests/test_intents_ola_a.py) | `uv run python -m pytest -q gateway/tests/test_intents_ola_a.py -k t04` | `passed`; la hidratación usa `description` y `acceptance_criteria` desde GitHub/Jira. |
| T05 | [`docs/gateway-central-deployment-runbook.md`](./gateway-central-deployment-runbook.md) | `uv run python -m pytest -q gateway/tests/test_ola_b.py -k t05` | `passed`; existe runbook y scripts de despliegue/smoke del gateway central. |
| T06 | [`docs/feedback-retry-policy.md`](./feedback-retry-policy.md) | `uv run python -m pytest -q gateway/tests/test_ola_b.py -k t06` | `passed`; feedback externo usa retry/backoff configurable por provider. |
| T07 | [`docs/smoke-ci-clean-contract.md`](./smoke-ci-clean-contract.md) | `python3 -m pytest -q flowctl/test_ci_integration_ola_c.py -k t07` | `passed`; el contrato oficial de `smoke:ci-clean` quedó fijado con keywords y payload JSON. |
| T08 | [`.github/workflows/root-ci.yml`](/Users/john/Projects/Personal/softos-sdd-orchestrator/.github/workflows/root-ci.yml) | `python3 -m pytest -q flowctl/test_ci_integration_ola_c.py -k t08` | `passed`; root CI ejecuta `flow ci integration --profile smoke:ci-clean --auto-up`. |
| T09 | [`flow`](/Users/john/Projects/Personal/softos-sdd-orchestrator/flow) | `python3 -m pytest -q flowctl/test_ci_integration_ola_c.py -k t09` | `passed`; `--bootstrap-runtime` quedó expuesto y documentado. |
| T10 | [`flowctl/ci.py`](/Users/john/Projects/Personal/softos-sdd-orchestrator/flowctl/ci.py) | `python3 -m pytest -q flowctl/test_ci_integration_ola_c.py -k t10` | `passed`; `smoke:ci-clean` usa preflight estricto por defecto con bypass controlado. |
| T11 | [`flowctl/ci.py`](/Users/john/Projects/Personal/softos-sdd-orchestrator/flowctl/ci.py) | `python3 -m pytest -q flowctl/test_ci_integration_ola_c.py -k t11` | `passed`; health/smoke aceptan overrides y backoff por servicio. |
| T12 | [`gateway/app/intents.py`](../gateway/app/intents.py) | `uv run python -m pytest -q gateway/tests/test_ola_b.py -k t12` | `passed`; GitHub `pull_request` nativo se parsea para `opened`, `edited` y `labeled`. |
| T13 | [`workspace.providers.json`](/Users/john/Projects/Personal/softos-sdd-orchestrator/workspace.providers.json) | `uv run python -m pytest -q gateway/tests/test_ola_b.py -k t13` | `passed`; Jira soporta `acceptance_criteria_field` configurable. |
| T14 | [`flowctl/operations.py`](/Users/john/Projects/Personal/softos-sdd-orchestrator/flowctl/operations.py) | `python3 ./flow ops metrics --json` | `gateway_tasks.by_intent_provider` publica `failure_rate` y `p95_latency_seconds`. |
| T15 | [`gateway/app/main.py`](../gateway/app/main.py) | `uv run python -m pytest -q gateway/tests/test_ola_d.py -k t15` | `passed`; existe `/v1/ops/monitor` como vista mínima operativa. |
| T16 | [`gateway/app/transforms.py`](../gateway/app/transforms.py) | `uv run python -m pytest -q gateway/tests/test_ola_d.py -k t16` | `passed`; las reglas transform declarativas se cargan desde config. |
| T17 | [`gateway/app/feedback.py`](../gateway/app/feedback.py) | `uv run python -m pytest -q gateway/tests/test_ola_d.py -k t17` | `passed`; hay plantillas de feedback por intent configurables. |
| T18 | [`gateway/app/spec_quality.py`](../gateway/app/spec_quality.py) | `uv run python -m pytest -q gateway/tests/test_ola_d.py -k t18` | `passed`; hay lint mínimo de estilo/ortografía para specs inbound. |
| T19 | [`gateway/app/flow_command.py`](../gateway/app/flow_command.py) | `uv run python -m pytest -q gateway/tests/test_ola_d.py -k t19` | `passed`; parseo de intents y construcción de comando quedaron separados. |
| T20 | [`gateway/app/intake_idempotency.py`](../gateway/app/intake_idempotency.py) | `uv run python -m pytest -q gateway/tests/test_ola_d.py -k t20` | `passed`; existe dedupe/idempotencia de intake con prueba de concurrencia. |
| T21 | [`docs/secret-scan-tuning.md`](./secret-scan-tuning.md) | `python3 ./flow secrets scan --all --json` | `blocking_findings: []`; la calibración de placeholders y falsos positivos quedó documentada y limpia. |
| T22 | [`docs/gateway-sla-incidents.md`](./gateway-sla-incidents.md) | `python3 ./flow ops sla --json` | `gateway_processing` publica umbrales de p95/failure_rate y guía de incidentes operativos. |
| T23 | [`docs/flow-reports-retention.md`](./flow-reports-retention.md) | `uv run python -m pytest -q gateway/tests/test_ola_d.py -k t23` | `passed`; la política de retención y el script de limpieza quedaron fijados. |
| T24 | [`docs/playbook-workflow-rollback.md`](./playbook-workflow-rollback.md) | `uv run python -m pytest -q gateway/tests/test_ola_d.py -k t24` | `passed`; el playbook de rollback quedó publicado con validación dry-run. |
| T25 | [`docs/onboarding-team-checklist.md`](./onboarding-team-checklist.md) | `uv run python -m pytest -q gateway/tests/test_ola_d.py -k t25` | `passed`; el checklist operativo de onboarding quedó fijado. |

## Uso

- Esta matriz es el punto único de referencia para evidencias Txx ya cerradas dentro de la ola de cierre.
- Si una fila cambia, la modificación debe conservar el archivo, el comando reproducible y un resultado verificable.
