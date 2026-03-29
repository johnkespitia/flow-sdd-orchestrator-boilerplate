# Matriz de evidencia de cierre del programa

Esta tabla fija la evidencia versionada de los ítems de cierre ya resueltos en `softos-program-closure-and-operational-readiness`.
La intención es que el artefacto sea consumible por humanos y verificable por CI, sin depender de estado efímero en `.flow/**`.

| Txx | archivo | test/comando | resultado |
| --- | --- | --- | --- |
| T22 | [`docs/gateway-sla-incidents.md`](./gateway-sla-incidents.md) | `python3 ./flow ops sla --json` | `gateway_processing` publica umbrales de p95/failure_rate y guía de incidentes operativos. |
| T23 | [`docs/flow-reports-retention.md`](./flow-reports-retention.md) | `python3 -m pytest -q gateway/tests/test_ola_d.py -k t23` | `2 passed`; la política de retención y el script de limpieza quedaron fijados. |
| T24 | [`docs/playbook-workflow-rollback.md`](./playbook-workflow-rollback.md) | `python3 -m pytest -q gateway/tests/test_ola_d.py -k t24` | `passed`; el playbook de rollback quedó publicado con validación dry-run. |
| T25 | [`docs/onboarding-team-checklist.md`](./onboarding-team-checklist.md) | `python3 -m pytest -q gateway/tests/test_ola_d.py -k t25` | `passed`; el checklist operativo de onboarding quedó fijado. |

## Uso

- Esta matriz es el punto único de referencia para evidencias Txx ya cerradas dentro de la ola de cierre.
- Si una fila cambia, la modificación debe conservar el archivo, el comando reproducible y un resultado verificable.
