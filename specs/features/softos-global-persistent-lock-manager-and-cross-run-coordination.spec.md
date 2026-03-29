---
schema_version: 3
name: SoftOS Global Persistent Lock Manager And Cross Run Coordination
description: Introducir coordinacion global persistente entre workflow runs para evitar colisiones cross-run sin degradar el paralelismo por slices
status: approved
owner: platform
single_slice_reason: ""
multi_domain: false
phases:
  - foundation
  - integration
  - operations
depends_on:
  - ../../specs/000-foundation/spec-as-source-operating-model.spec.md
  - ../../specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - ../../specs/features/softos-central-spec-registry-and-claiming.spec.md
  - ../../specs/features/softos-autonomous-sdlc-execution-engine.spec.md
  - ../../specs/features/softos-multiagent-concurrency-and-locking.spec.md
  - ../../specs/features/softos-rollback-retry-and-recovery.spec.md
required_runtimes: []
required_services: []
required_capabilities: []
stack_projects: []
stack_services: []
stack_capabilities: []
targets:
  - ../../flow
  - ../../flowctl/locks.py
  - ../../flowctl/test_global_locks.py
  - ../../flowctl/multiagent.py
  - ../../flowctl/test_multiagent.py
  - ../../flowctl/workflows.py
  - ../../flowctl/test_workflow_engine.py
  - ../../docs/global-lock-manager.md
---

# SoftOS Global Persistent Lock Manager And Cross Run Coordination

## Objetivo

Garantizar que dos `workflow run` distintos no ejecuten slices incompatibles sobre el mismo repo o `hot_area` sin coordinacion global, manteniendo el paralelismo fino dentro de una misma spec cuando los locks no colisionan.

## Contexto

- Hoy el scheduler multiagent coordina bien las slices dentro de una sola ejecucion porque mantiene `lock_table` en memoria durante `run_slice_scheduler`.
- Ese modelo no se comparte entre procesos distintos, por lo que dos `workflow run` simultaneos pueden intentar tomar el mismo repo, la misma `hot_area` o el mismo `semantic_lock` sin arbitraje global persistente.
- La spec `softos-multiagent-concurrency-and-locking` ya cubre paralelismo intra-run, capacidad por repo y DLQ, pero no exige coordinacion transaccional entre runs separados.
- La spec `softos-central-spec-registry-and-claiming` ya introduce ownership transaccional para la spec completa; falta el equivalente operativo a nivel slice/lock para el plano de ejecucion.
- La gobernanza nueva de `Slice Breakdown` y `hot_area` ya permite modelar mejor la intencion de concurrencia. Esta spec convierte esa señal de planificacion en control de ejecucion persistente.

## Foundations Aplicables

- `specs/000-foundation/spec-as-source-operating-model.spec.md`: la spec sigue siendo la fuente de verdad del alcance, los locks y la estrategia de coordinacion.
- `specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md`: el mecanismo debe vivir en el runtime operativo de SoftOS y dejar reportes reproducibles en `.flow/reports/**`.

## Domains Aplicables

- no aplica domain porque esta feature pertenece al dominio transversal de orquestacion del SDLC y no a un dominio funcional de producto en `specs/domains/**`

## Problema a resolver

- Dos specs distintas pueden correr en paralelo sobre el mismo workspace y el mismo repo sin verse entre si.
- El aislamiento actual depende de worktrees y del orden local del scheduler, pero no existe una tabla global compartida con ownership, TTL ni heartbeat entre procesos.
- Un crash o corte abrupto puede dejar incertidumbre operativa: otro run no sabe si un lock sigue vivo, si puede reclamarse o si debe esperar.
- El scheduler actual no distingue entre esperas locales de la cola y bloqueos globales producidos por otro run, por lo que la observabilidad y el recovery quedan incompletos.

## Alcance

### Incluye

- backend persistente de locks globales compartido entre `workflow run`
- identificador `run_id` estable por ejecucion para ownership de locks y auditoria
- adquisicion de locks globales antes de ejecutar una slice
- soporte inicial para `semantic_lock`, `hot_area` y fallback conservador por repo cuando falte modelado valido
- heartbeat y expiracion por TTL para recuperar locks huerfanos
- razones explicitas de espera global en reportes del scheduler y del workflow engine
- liberacion deterministica de locks en exito, fallo y cancelacion
- comandos o funciones internas suficientes para inspeccionar el estado actual de locks y eventos relevantes

### No incluye

- coordinacion distribuida entre multiples maquinas o workspaces remotos
- fairness compleja o algoritmo de prioridades globales sofisticado
- auto-descubrimiento inteligente de `hot_area` cuando la spec este mal modelada
- reemplazo total del scheduler actual ni reescritura del engine de workflows

## Repos afectados

| Repo | Targets |
| --- | --- |
| `root` | `../../flow`, `../../flowctl/**`, `../../docs/**` |

## Resultado esperado

- SoftOS puede correr dos specs en paralelo en el mismo workspace siempre que no compitan por la misma `hot_area` o `semantic_lock`.
- Cuando dos runs colisionan, solo uno adquiere el lock y el otro queda en espera global con razon deterministica y visible.
- Si un proceso muere sin liberar, el lock expira por TTL y puede ser recuperado sin limpieza manual riesgosa.
- Los reportes distinguen claramente esperas locales del scheduler y bloqueos globales cross-run.

## Reglas de negocio

- Todo `workflow run` debe generar y propagar un `run_id` unico antes de iniciar slices.
- Ninguna slice puede ejecutar `start_slice_callable` si no adquirio todos sus locks globales requeridos.
- `semantic_lock` tiene prioridad sobre `hot_area` y ambos tienen prioridad sobre el fallback por repo.
- El fallback por repo solo aplica a slices legacy o mal modeladas que no declaren `hot_area` utilizable.
- Todo lock persistente debe registrar `owner_run_id`, `owner_feature`, `owner_slice`, `acquired_at`, `heartbeat_at` y `expires_at`.
- Un lock expirado puede ser reclamado por otro run sin intervencion manual, pero el evento debe quedar auditado.
- La liberacion de locks debe ocurrir en `finally` o via compensacion equivalente incluso si la slice falla.
- El sistema debe exponer la diferencia entre `wait_local_capacity`, `wait_dependency` y `wait_global_lock`.

## Flujo principal

1. `flow workflow run <slug>` crea un `run_id` y lo adjunta al estado de la ejecucion.
2. El planner materializa slices con `hot_area`, `depends_on` y `semantic_locks` desde la spec aprobada.
3. El scheduler local determina que una slice esta lista a nivel DAG y capacidad intra-run.
4. Antes de arrancar la slice, el lock manager persistente intenta adquirir todos los locks globales requeridos.
5. Si la adquisicion falla, la slice queda en espera con razon global, owner actual y momento estimado de expiracion si existe.
6. Si la adquisicion tiene exito, la slice ejecuta normalmente y renueva heartbeat mientras este activa.
7. Al terminar o fallar, el engine libera los locks adquiridos y publica el evento en reportes.
8. Si el proceso muere y deja locks huerfanos, otro run puede expirarlos y reclamarlos segun TTL.

## Contrato funcional

- Inputs clave:
  - `run_id`
  - `feature_slug`
  - `slice_name`
  - `repo`
  - `hot_area`
  - `semantic_locks`
  - `lock_ttl_seconds`
- Outputs clave:
  - resultado de `acquire` con `granted`, `wait_reason`, `blocking_owner`, `expires_at`
  - eventos de `heartbeat`, `release` y `expire`
  - estado agregado en reportes de scheduler y workflow
- Errores esperados:
  - intento de adquirir lock ya tomado por otro run
  - heartbeat sobre lock no poseido o expirado
  - release idempotente sobre lock ya liberado
  - corrupcion o indisponibilidad del store persistente
- Side effects relevantes:
  - escritura transaccional en store de locks
  - generacion de auditoria operativa
  - posible reordenamiento de slices disponibles por bloqueo global

## Decisiones de diseno

- El store persistente inicial debe ser SQLite local al workspace y no un diccionario en memoria.
- El store de locks debe vivir separado del scheduler para mantener responsabilidades claras y permitir evolucion independiente.
- La primera version debe operar en un solo workspace/host; coordinacion multi-host queda fuera de alcance.
- El scheduler actual se conserva para concurrencia intra-run; la coordinacion global se agrega como backend de locks, no como reemplazo del scheduler.
- La politica recomendada es hibrida:
  - lock obligatorio por `semantic_lock`
  - lock obligatorio por `hot_area`
  - fallback por repo solo cuando la slice no tenga `hot_area` valida

## Modelo de datos minimo

- Tabla o entidad `global_locks` con:
  - `lock_name`
  - `scope`
  - `repo`
  - `owner_run_id`
  - `owner_feature`
  - `owner_slice`
  - `acquired_at`
  - `heartbeat_at`
  - `expires_at`
- Tabla o entidad `global_lock_events` con:
  - `event_id`
  - `lock_name`
  - `event_type`
  - `actor_run_id`
  - `feature_slug`
  - `slice_name`
  - `timestamp`
  - `details`

## Routing de implementacion

- El repo se deduce desde `targets`.
- La implementacion principal vive en `flowctl`.
- `flowctl/locks.py` o modulo equivalente concentra persistencia y arbitraje.
- `flowctl/multiagent.py` consulta el backend global antes de arrancar trabajo.
- `flowctl/workflows.py` genera `run_id`, integra heartbeat/release y serializa reportes.
- `docs/**` documenta operacion, recovery y limites conocidos.

## Slice Breakdown

```yaml
- name: persistent-lock-backend
  targets:
    - ../../flowctl/locks.py
    - ../../flowctl/test_global_locks.py
  hot_area: flowctl/locks
  depends_on: []
- name: scheduler-global-lock-integration
  targets:
    - ../../flowctl/multiagent.py
    - ../../flowctl/test_multiagent.py
  hot_area: flowctl/multiagent
  depends_on:
    - persistent-lock-backend
- name: workflow-run-identity-and-recovery
  targets:
    - ../../flow
    - ../../flowctl/workflows.py
    - ../../flowctl/test_workflow_engine.py
  hot_area: flowctl/workflows
  depends_on:
    - persistent-lock-backend
    - scheduler-global-lock-integration
- name: docs-and-operability
  targets:
    - ../../docs/global-lock-manager.md
  hot_area: docs/global-lock-manager
  depends_on:
    - persistent-lock-backend
```

## Criterios de aceptacion

- Dos procesos concurrentes intentando adquirir el mismo `semantic_lock` producen un solo ganador y un rechazo deterministico para el otro.
- Dos runs sobre el mismo repo y distintas `hot_area` pueden progresar en paralelo sin lock global por repo.
- Una slice sin `hot_area` valida cae en fallback conservador por repo y lo reporta explicitamente.
- Un lock expirado por ausencia de heartbeat puede ser reclamado por otro run sin dejar ownership ambiguo.
- El scheduler report distingue `wait_global_lock` de waits locales por capacidad o dependencias.
- `workflow run` y `slice_start` conservan auditoria suficiente para reconstruir quien tomo, renovo, libero o expiro un lock.
- La falla del backend persistente aborta la ejecucion insegura en lugar de degradar silenciosamente a memoria local.

## Test plan

- [@test] ../../flowctl/test_global_locks.py
- [@test] ../../flowctl/test_multiagent.py
- [@test] ../../flowctl/test_workflow_engine.py

## Riesgos y mitigaciones

- Riesgo: serializar demasiado por usar lock por repo como default.
  - Mitigacion: limitar el fallback por repo a specs legacy o slices sin `hot_area` valida.
- Riesgo: TTL demasiado corto roba locks de procesos vivos pero lentos.
  - Mitigacion: heartbeat periodico y configuracion explicita de `lock_ttl_seconds`.
- Riesgo: SQLite local no resuelve coordinacion multi-host futura.
  - Mitigacion: aislar el backend detras de una interfaz para poder migrarlo despues.
- Riesgo: observabilidad incompleta complica recovery.
  - Mitigacion: registrar eventos separados de acquire, heartbeat, release y expire.

## Rollout

- activar primero el backend persistente detras de feature flag o configuracion operativa
- habilitar `semantic_lock` y `hot_area` persistentes antes de forzar fallback por repo
- validar con dos specs de prueba concurrentes en el mismo workspace
- documentar procedimiento de inspeccion y limpieza segura antes de declararlo default

## Rollback

- desactivar el backend persistente via configuracion y volver temporalmente al comportamiento intra-run actual
- conservar las tablas o archivos de eventos para auditoria post-mortem
- no eliminar ni reescribir reportes previos al rollback
