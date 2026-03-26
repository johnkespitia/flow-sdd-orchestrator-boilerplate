## SoftOS Operations Runbook

### 1. Métricas operativas (`/metrics` en gateway + `flow ops metrics`)

- **Comando CLI preferido**:

```bash
python3 ./flow ops metrics --json
```

Salida mínima:

- `throughput`: número de workflow runs completados.
- `failure_rate`: fracción de runs fallidos.
- `stage_latency`: arreglo `{stage, avg_seconds, samples}`.
- `retries`: total de reintentos por etapas (suma de `attempt - 1`).
- `dlq_size`: entradas totales en DLQ (workflow + scheduler).

- **Endpoint HTTP `/metrics` (gateway)**:

  - El servicio `gateway/` expone:

```bash
GET /metrics
```

  - Devuelve un JSON equivalente a `flow ops metrics --json`, alimentado desde el workspace raiz (archivos `.flow/reports/workflows/*-workflow-run.json` y scheduler).
  - Se recomienda apuntar tus dashboards y sistemas de alertas a este endpoint HTTP.

### 2. Dashboard de runs (`flow ops dashboard`)

Comando:

```bash
python3 ./flow ops dashboard --json
```

Para cada `feature` muestra:

- `engine_status`: estado actual del motor (`completed|failed|paused|...`).
- `updated_at`, `paused_at_stage`.
- `stages`: lista de `{stage, status, attempt, failure_reason}`.

Uso recomendado:

- Identificar rápidamente runs:
  - en fallo (`engine_status = failed`).
  - con muchos reintentos (`attempt` alto).
  - con etapas `skipped` en momentos inesperados.

### 3. SLA por etapa y alertas persistidas

#### Evaluación de SLA

Comando:

```bash
python3 ./flow ops sla --json
```

Esto:

- Usa las latencias de `flow ops metrics`.
- Evalúa thresholds por etapa (config base en código, futura configuración vía `workspace.config.json`).
- Escribe/actualiza:

```text
.flow/reports/operations/sla-alerts.json
```

Estructura mínima de alerta:

```json
{
  "feature": "*",
  "stage": "ci_repo",
  "observed_latency": 1400.0,
  "threshold": 600.0,
  "severity": "warning|critical",
  "timestamp": "2026-03-26T21:44:41+00:00",
  "status": "open"
}
```

Interpretación:

- `severity = warning` si se excede el threshold.
- `severity = critical` si `observed_latency >= 2 * threshold`.

### 4. Bitácora de decisiones agente-humano

#### Alta de decisiones

Comando:

```bash
python3 ./flow ops decision-log add \
  --actor-type human \
  --actor "<id-or-nombre>" \
  --decision "<resumen>" \
  --context "<contexto breve>" \
  --impact-or-risk "<bajo|medio|alto>" \
  --json
```

Cada entrada se persiste en:

```text
.flow/reports/operations/decisions.jsonl
```

Campos obligatorios:

- `actor_type`: `agent|human`.
- `actor`: identificador del actor.
- `decision`: resumen claro de la decisión.
- `context`: por qué/cuándo se tomó.
- `impact_or_risk`: impacto o riesgo percibido.
- `timestamp`: ISO8601 UTC.

#### Consulta de decisiones

Comando:

```bash
python3 ./flow ops decision-log list --limit 100 --json
```

Devuelve:

```json
{
  "generated_at": "2026-03-26T21:44:52+00:00",
  "items": [
    {
      "actor_type": "human",
      "actor": "demo-user",
      "decision": "pause-ci",
      "context": "manual triage",
      "impact_or_risk": "low",
      "timestamp": "2026-03-26T21:44:47+00:00"
    }
  ]
}
```

Uso recomendado:

- Conectar decisiones clave (pausar release, forzar retry, saltar etapa) con:
  - runs y etapas en `ops dashboard`.
  - SLAs y alertas en `sla-alerts.json`.

### 5. Flujo de triage operativo

1. **Detección**
   - Monitorizar `/metrics` o `flow ops metrics --json` en dashboards externos.
   - Configurar alertas por:
     - aumento de `failure_rate`.
     - `dlq_size` creciendo.
     - latencias en etapas críticas (`ci_repo`, `ci_integration`).

2. **Inspección inicial**
   - Ejecutar `flow ops dashboard --json`:
     - localizar `features` con `engine_status = failed`.
     - inspeccionar `stages` con `status = failed` o `attempt` alto.

3. **Revisar SLAs**
   - Ejecutar `flow ops sla --json`.
   - Abrir `.flow/reports/operations/sla-alerts.json`:
     - priorizar `severity = critical`.

4. **Contexto y decisiones**
   - Usar:
     - `flow workflow run <slug> --json` para detalles del run.
     - `flow ops decision-log list --json` para ver quién tomó qué decisiones recientes.

5. **Acciones recomendadas por tipo de alerta**

- **Fallo frecuente en `ci_repo`**:
  - Revisar `workflow_dlq` y `rollback` del run.
  - Decidir (y registrar en `decision-log add`) si:
    - pausar temporalmente el pipeline.
    - reducir alcance de cambios.

- **Latencias altas en `ci_integration`**:
  - Verificar estado de stack (`flow stack ps`, `flow ci integration`).
  - Evaluar necesidad de escalar recursos o ajustar perfiles.

- **DLQ creciente**:
  - Revisar `*-scheduler.json` (`dlq`, `locks`, `lock_events`).
  - Ejecutar acciones manuales sobre slices problemáticas, registrando cada decisión en la bitácora.

6. **Cierre**
   - Una vez mitigado el incidente:
     - actualizar la bitácora con decisión de cierre.
     - volver a ejecutar `flow ops metrics` y `flow ops sla` para confirmar vuelta a parámetros normales.

