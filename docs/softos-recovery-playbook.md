## SoftOS Recovery Playbook

### 1. Clasificación de fallos

`workflow_run` clasifica cada fallo de etapa en una de estas clases de error:

- **infra**: fallos de infraestructura / entorno de ejecución (por ejemplo `infra_apply`, `ci_integration`).
- **dependencia**: fallos derivados de repos/servicios dependientes (`ci_spec`, `ci_repo`, `dependency-failed:*`).
- **validacion**: fallos de checkpoints de calidad (drift, contratos, confianza, reviewers adicionales).
- **logica**: resto de fallos de negocio/orquestación no cubiertos por las anteriores.

La clase se expone en:

- `state.workflow_engine.stages[stage].error_class`
- `workflow_run.payload.stages[*].error_class`
- `workflow_run.payload.workflow_dlq[*].error_class`

### 2. Retry policy por clase

Configuración en `workspace.config.json`:

```json
{
  "project": {
    "workflow": {
      "retry_policy": {
        "infra":        { "max_attempts": 3, "backoff_seconds": 0, "jitter_seconds": 0 },
        "dependencia":  { "max_attempts": 2, "backoff_seconds": 0, "jitter_seconds": 0 },
        "validacion":   { "max_attempts": 0, "backoff_seconds": 0, "jitter_seconds": 0 },
        "logica":       { "max_attempts": 0, "backoff_seconds": 0, "jitter_seconds": 0 }
      }
    }
  }
}
```

Reglas:

- `max_attempts` incluye el primer intento (p.ej. `2` ⇒ 1 fallo + 1 retry).
- Entre intentos:
  - `sleep_seconds = backoff_seconds + effective_jitter`
  - `effective_jitter = min(jitter_seconds, attempt - 1)` (determinista y testeable).
- La política se evalúa por etapa según su `error_class`.

### 3. Flujo de rollback por etapa

Cuando `workflow_run` termina en `status = "failed"`:

1. El engine ejecuta rollback por etapas en orden de ejecución (`WORKFLOW_ENGINE_STAGES`).
2. Solo se consideran etapas con `status = "passed"`.
3. El resultado se persiste en:

```json
"workflow_engine": {
  "rollback": {
    "status": "idle|completed|partial|failed",
    "summary": "texto resumido",
    "updated_at": "ISO8601",
    "stages": {
      "<stage>": {
        "stage_name": "<stage>",
        "status": "completed|skipped|failed|partial",
        "compensated_at": "ISO8601",
        "failure_reason": "opcional",
        "pending_actions": [ { "kind": "...", "reason": "...", ... } ]
      }
    },
    "reverted_items": [ { "stage": "...", "action": "...", ... } ],
    "pending_items": [ { "kind": "...", "reason": "...", ... } ],
    "manual_actions_required": true
  }
}
```

#### Etapas con compensaciones operativas

- **`slice_start`**
  - Fuente de verdad: reporte del scheduler `workflows/<slug>-scheduler.json`.
  - Si `dlq` está vacío:
    - `rollback.stages.slice_start.status = "completed"`
    - `rollback.pending_items` no recibe entradas de slices.
  - Si `dlq` tiene entradas:
    - `rollback.stages.slice_start.status = "partial"`
    - Cada item de `dlq` se copia a `rollback.pending_items` con:
      - `kind = "slice"`
      - `slice`, `reason`, `attempt`
    - `rollback.manual_actions_required = true`.
  - No se tocan repos/producto: las compensaciones son puramente operativas y de reporte.

- **`release_promote`, `infra_apply`**
  - Hoy no tienen compensación implementada dentro de este workspace.
  - El rollback las marca como:
    - `status = "skipped"`
    - `pending_actions = []`
    - `reverted_items[*].reason = "no-compensation-implemented-in-this-scope"`.

Todas las demás etapas:

- `status = "skipped"`
- Acción de tipo `no-op` documentada.

El rollback es idempotente: reintentar `workflow_run` después de un fallo no duplica compensaciones ya registradas.

### 4. Criterio de reassignment safe

En el reporte JSON de `workflow_run` se incluyen:

```json
{
  "reassignment_ready": true,
  "reassignment_reason": "string opcional"
}
```

Reglas mínimas:

- `reassignment_ready` es `true` **solo si**:
  - `engine_status == "failed"`.
  - `workflow_engine.rollback.status` ∈ `{ "idle", "completed" }`.
  - `workflow_engine.rollback.pending_items` está vacío.
  - `workflow_run.workflow_dlq` está vacío.
  - (Si existe scheduler report) `jobs` no contienen estados `pending|running`.
- Si alguna condición no se cumple:
  - `reassignment_ready = false`.
  - `reassignment_reason` explica el motivo (`engine-not-failed`, `rollback-status:partial`, `workflow-dlq-has-items`, etc.).

Uso recomendado:

- Solo reasignar a otro agente/equipo cuando `reassignment_ready = true`.
- En caso contrario:
  - Consultar `rollback.pending_items` y `workflow_dlq`.
  - Ejecutar acciones manuales antes de volver a disparar el workflow.

### 5. Uso de DLQ

#### Scheduler DLQ (nivel slice)

- Ubicación: `workflows/<slug>-scheduler.json`.
- Campo: `dlq: [{ "slice", "reason", "attempt" }]`.
- Refleja slices que agotaron retries internos del scheduler.
- El rollback de `slice_start` traduce esta información a `rollback.pending_items`.

#### Workflow DLQ (nivel etapa)

- Campo en reporte `workflow_run`: `workflow_dlq: [{ ... }]`.
- Estructura:

```json
{
  "feature": "<slug>",
  "stage": "<stage_name>",
  "error_class": "<infra|dependencia|validacion|logica>",
  "attempts": 3,
  "failure_reason": "stage `<stage>` failed with exit code 1.",
  "timestamp": "ISO8601"
}
```

Uso:

- Es la fuente de verdad para etapas que agotaron la política de retry.
- Debe consultarse junto con:
  - `stages[*].status` y `error_class`
  - `rollback.pending_items`

### 6. Checklist manual de recovery

1. **Identificar el fallo**
   - Ejecutar `python3 ./flow workflow run <slug> --json` o revisar el último reporte `.flow/reports/workflows/<slug>-workflow-run.json`.
   - Confirmar `status = "failed"`.
2. **Revisar retry / DLQ**
   - Revisar `workflow_dlq` para entender:
     - etapa, clase de error, attempts, `failure_reason`.
   - Revisar `rollback.summary` y `rollback.stages`.
3. **Analizar slices pendientes**
   - Abrir `workflows/<slug>-scheduler.json`.
   - Revisar:
     - `dlq` (slices que fallaron repetidamente).
     - `locks` y `lock_events` (posibles conflictos de semáforos).
   - Seguir `rollback.pending_items` para ver qué slices requieren atención.
4. **Tomar acciones manuales mínimas**
   - Decidir por cada slice en DLQ:
     - Reintentar manualmente (p.ej. `flow slice start`).
     - Cerrarla y crear una nueva slice/story.
   - Documentar las decisiones en el reporte operativo del equipo.
5. **Verificar que el sistema está en estado estable**
   - Confirmar:
     - No hay jobs `pending|running` en el scheduler.
     - `workflow_engine.rollback.pending_items` está vacío.
     - `workflow_run.workflow_dlq` refleja solo histórico o está vacío.
6. **Reasignar si corresponde**
   - Comprobar `reassignment_ready`:
     - Si `true`: es seguro handoff a otro agente/equipo.
     - Si `false`: seguir la pista en `reassignment_reason` y volver al paso 3.
7. **Reintentar workflow**
   - Una vez resueltos los pendientes:
     - Ejecutar de nuevo `python3 ./flow workflow run <slug> --json` o usar `workflow retry`/`resume` según convenga.

