# Gateway sla incidents

English source: [docs/gateway-sla-incidents.md](../gateway-sla-incidents.md)

Source: `docs/gateway-sla-incidents.md`  
Last updated: 2026-05-06

Nota: Este espejo en espanol fue creado para cerrar el backlog de i18n. Se recomienda refinar la traduccion en una iteracion posterior.

# SLA de procesamiento de tasks (gateway) y política de incidentes (T22)

Spanish mirror: [docs/es/gateway-sla-incidents.es.md](./es/gateway-sla-incidents.es.md)

Source: `docs/gateway-sla-incidents.md`  
Last updated: 2026-05-06

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
