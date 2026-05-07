# Global lock manager

English source: [docs/global-lock-manager.md](../global-lock-manager.md)

Source: `docs/global-lock-manager.md`  
Last updated: 2026-05-06

Nota: Este espejo en espanol fue creado para cerrar el backlog de i18n. Se recomienda refinar la traduccion en una iteracion posterior.

# Global Lock Manager

Spanish mirror: [docs/es/global-lock-manager.es.md](./es/global-lock-manager.es.md)

Source: `docs/global-lock-manager.md`  
Last updated: 2026-05-06

## Objetivo

Coordinar locks persistentes entre `workflow run` distintos para evitar colisiones cross-run sobre el mismo `semantic_lock`, `hot_area` o repo legacy sin desactivar el paralelismo fino dentro de una misma spec.

## Estado actual

La implementación actual ya cubre:

- backend SQLite persistente en `flowctl/locks.py`
- integración opt-in del scheduler en `flowctl/multiagent.py`
- `run_id` persistente por workflow en `flowctl/workflows.py`
- waits explícitos `wait-global-lock:<lock>`

Límite conocido:

- el backend es local al workspace y a una sola máquina
- no coordina múltiples hosts ni múltiples workspaces remotos

## Backend persistente

- DB por defecto: `.flow/state/locks.db`
- tablas:
  - `global_locks`
  - `global_lock_events`
- adquisición transaccional con SQLite `BEGIN IMMEDIATE`
- `busy_timeout = 5000` para reducir contención espuria

## Tipos de lock

| Lock type | Cuándo aplica | Ejemplo |
| --- | --- | --- |
| `semantic:<name>` | Cuando la slice declara `semantic_locks` | `semantic:db:migrations` |
| `hot-area:<repo>:<path>` | Cuando la slice declara o infiere `hot_area` | `hot-area:root:flowctl/workflows` |
| `repo:<repo>` | Fallback para slices legacy sin `hot_area` utilizable | `repo:root` |

Prioridad:

1. `semantic_lock`
2. `hot_area`
3. fallback por repo

## Flujo operativo

1. `workflow run` genera o reutiliza un `run_id`.
2. `slice_start` recalcula plan y scheduler.
3. Antes de arrancar una slice, el scheduler intenta adquirir locks globales.
4. Si el lock está tomado por otro run, la slice queda en wait con razón `wait-global-lock:<lock>`.
5. Mientras la slice corre, el scheduler renueva heartbeat.
6. Al finalizar, libera los locks adquiridos.
7. Si un proceso muere, otro run puede expirar locks huérfanos por TTL.

## Configuración

Variables relevantes:

- `FLOW_SCHEDULER_LOCK_TTL_SECONDS`
- `FLOW_SCHEDULER_MAX_WORKERS`
- `FLOW_SCHEDULER_PER_REPO_CAPACITY`
- `FLOW_SCHEDULER_PER_HOT_AREA_CAPACITY`

Valores por defecto relevantes:

- TTL mínimo efectivo: `5s` en el wiring del workflow
- workers: `4`
- capacidad por repo: `1`
- capacidad por hot area: `1`

## Observabilidad

El scheduler report expone:

- `waits`
- `locks`
- `lock_events`
- `dlq`

Eventos típicos:

- `acquire`
- `denied`
- `heartbeat`
- `release`
- `expire`

Rutas útiles:

- `.flow/reports/workflows/<slug>-scheduler.json`
- `.flow/reports/workflows/<slug>-workflow-run.json`
- `.flow/state/locks.db`

## Diagnóstico rápido

### Verificar que el workflow usa `run_id`

```bash
python3 ./flow workflow run <slug> --json
```

Buscar:

- `run_id` en el payload final

### Confirmar waits globales

```bash
python3 ./flow workflow run <slug> --json
```

Luego revisar en el scheduler report:

- `wait-global-lock:semantic:...`
- `wait-global-lock:hot-area:...`
- `wait-global-lock:repo:...`

### Inspeccionar la base de locks

```bash
sqlite3 .flow/state/locks.db "select lock_name, scope, repo, owner_run_id, owner_feature, owner_slice, expires_at from global_locks order by lock_name;"
sqlite3 .flow/state/locks.db "select event_id, lock_name, event_type, actor_run_id, feature_slug, slice_name, timestamp from global_lock_events order by event_id desc limit 20;"
```

## Recovery

Si un run se cae y deja dudas de ownership:

1. revisar `global_locks`
2. revisar `global_lock_events`
3. confirmar si `expires_at` ya venció
4. rerun del workflow o `retry` de etapa para que el scheduler vuelva a reclamar

No se recomienda borrar filas manualmente salvo diagnóstico controlado.

## Pruebas relevantes

- `python3 -m pytest -q flowctl/test_global_locks.py`
- `python3 -m pytest -q flowctl/test_multiagent.py`
- `python3 -m pytest -q flowctl/test_multiagent_scheduler.py`
- `python3 -m pytest -q flowctl/test_workflow_engine.py`
