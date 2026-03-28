# SLA de procesamiento de tasks (gateway) y política de incidentes (T22)

## Métricas

- `GET /metrics` del gateway incluye `gateway_intent_metrics.by_intent_provider` con `avg_latency_seconds`, `p95_latency_seconds`, `failure_rate` por par `(source, intent)`.
- `python3 ./flow ops metrics --json` incluye `gateway_tasks` (misma agregación vía SQLite).
- `python3 ./flow ops sla --json` incluye `gateway_processing` con alertas cuando:
  - `p95_latency_seconds` > 3600 s (configurable en código `evaluate_gateway_task_processing_sla`), o
  - `failure_rate` > 0.25.

## Incidentes

1. **Detectar**: revisar alertas en `sla-alerts.json` / salida de `flow ops sla`.
2. **Contener**: pausar webhooks en origen o elevar `SOFTOS_GATEWAY_RATE_LIMIT_*` temporalmente.
3. **Comunicar**: entrada en `flow ops decision-log add` con contexto y actor.
4. **Resolver**: reintentar tasks fallidas desde worker o limpiar cola según runbook de rollback.

## Referencias

- `flowctl/operations.py` — `evaluate_gateway_task_processing_sla`
- `docs/playbook-workflow-rollback.md`
