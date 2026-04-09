---
schema_version: 3
name: "SoftOS slave autonomous intake polling"
description: "Permitir que un workspace slave opere un loop opt-in y acotado para descubrir trabajo elegible en gateway remoto, reclamarlo de forma auditable, materializar la spec canónica y detenerse bajo reglas explícitas de seguridad, backoff y ownership."
status: approved
owner: platform
single_slice_reason: ""
multi_domain: false
phases: []
depends_on:
  - specs/000-foundation/spec-as-source-operating-model.spec.md
  - specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - specs/000-foundation/repo-routing-and-worktree-orchestration.spec.md
  - specs/features/softos-remote-intake-claim-and-slave-execution-bridge.spec.md
  - specs/features/softos-slave-remote-operator-ergonomics.spec.md
  - specs/features/softos-slave-remote-governance-and-assisted-picking.spec.md
required_runtimes: []
required_services: []
required_capabilities: []
stack_projects: []
stack_services: []
stack_capabilities: []
targets:
  - ../../flow
  - ../../flowctl/gateway_ops.py
  - ../../flowctl/parser.py
  - ../../flowctl/test_gateway_ops.py
  - ../../docs/slave-remote-gateway-operator-runbook.md
  - ../../README.md
  - ../../workspace.config.json
  - ../../specs/features/softos-slave-autonomous-intake-polling.spec.md
---

# SoftOS slave autonomous intake polling

## Objetivo

Habilitar una ola controlada de autonomía para workspaces `slave` conectados a un gateway remoto,
permitiendo que el operator ejecute un loop opt-in que:

- consulte trabajo remoto elegible
- reclame una spec de forma exclusiva y auditable
- materialice la spec canónica localmente
- se detenga bajo reglas explícitas de stop, backoff y safety

La ola debe reducir trabajo manual repetitivo, pero sin convertir todavía al `slave` en un ejecutor
autónomo completo de `plan`, `slice start`, `slice verify`, `release` o cierre de workflow.

## Contexto

Las olas previas ya cerraron los fundamentos necesarios:

- el bridge remoto entre `flow` y gateway ya existe
- `claim`, `fetch-spec`, `heartbeat`, `transition`, `reassign` y `release` funcionan
- `flow gateway pick` ofrece selección asistida
- el ownership remoto ya tiene política mínima de autorización
- `slave` ya opera con `status/current`, auto-heartbeat y hooks SDLC controlados

Lo que todavía falta para una operación menos manual es un mecanismo de polling/cola acotado que no
exija al developer repetir `list` + `pick` de forma constante.

## Foundations Aplicables

- `specs/000-foundation/spec-as-source-operating-model.spec.md`
- `specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md`
- `specs/000-foundation/repo-routing-and-worktree-orchestration.spec.md`
- `specs/features/softos-remote-intake-claim-and-slave-execution-bridge.spec.md`
- `specs/features/softos-slave-remote-operator-ergonomics.spec.md`
- `specs/features/softos-slave-remote-governance-and-assisted-picking.spec.md`

## Domains Aplicables

- no aplica domain porque el cambio es de orquestación operativa del workspace

## Governing Decision

- la autonomía permitida en esta ola es de descubrimiento y claim, no de ejecución completa del SDLC
- el gateway sigue siendo la fuente de verdad del ownership remoto
- cada claim automático debe permanecer auditable e inequívoco
- el loop autónomo debe ser opt-in, acotado y cancelable
- el loop no puede reescribir prioridades ni usar heurísticas opacas

## Problema a resolver

El operator todavía debe hacer polling manual del gateway:

- mirar la lista remota
- elegir cuándo intentar `pick`
- repetir este ciclo hasta encontrar una spec libre

Eso introduce tiempo muerto y ruido operativo, sobre todo cuando el `slave` está dedicado a esperar
la siguiente spec elegible.

## Alcance

### Incluye

- comando one-shot tipo `flow gateway poll`
- loop opt-in tipo `flow gateway watch` o equivalente
- selección automática limitada a reglas determinísticas ya gobernadas
- backoff, jitter mínimo y stop conditions explícitas
- materialización local de la spec canónica tras claim exitoso
- salida estructurada y logs operativos comprensibles para el operator
- documentación del modo autónomo asistido

### No incluye

- ejecución automática de `plan`
- arranque automático de slices
- cierre automático o `release` automático
- scheduler multi-worker complejo
- fairness global entre múltiples gateways o múltiples tenants
- políticas de prioridad externas o scoring heurístico

## Repos afectados

| Repo | Targets |
| --- | --- |
| `sdd-workspace-boilerplate` | `../../flow`, `../../flowctl/gateway_ops.py`, `../../flowctl/parser.py`, `../../flowctl/test_gateway_ops.py`, `../../docs/slave-remote-gateway-operator-runbook.md`, `../../README.md`, `../../workspace.config.json`, `../../specs/features/softos-slave-autonomous-intake-polling.spec.md` |

## Resultado esperado

- el operator puede correr un polling one-shot para intentar reclamar una spec elegible
- el operator puede dejar un loop acotado esperando una spec sin intervención manual constante
- cada claim resultante queda auditado como claim explícito remoto
- la spec canónica se materializa localmente apenas se obtiene el claim
- el loop se detiene con mensajes claros cuando se alcanza un límite o una condición de stop

## Execution Surface Inventory

### Write paths obligatorios

- `flow`
- `flowctl/gateway_ops.py`
- `flowctl/parser.py`
- `flowctl/test_gateway_ops.py`
- `docs/slave-remote-gateway-operator-runbook.md`
- `README.md`
- `workspace.config.json`

### Read paths obligatorios

- `.flow/state/<slug>.json`
- `.env.gateway`
- `workspace.config.json`
- `specs/features/softos-slave-remote-governance-and-assisted-picking.spec.md`
- `specs/features/softos-slave-remote-operator-ergonomics.spec.md`

### Out of scope explícito

- `gateway/app/**`
- background daemon siempre encendido fuera del control del operator
- ejecución automática de `plan` o slices después del claim
- persistencia adicional de cola central en gateway
- cambios de RBAC externos

## Technical Observed Inventory

Superficies existentes que se deben reutilizar:

- `flowctl/gateway_ops.py`
  ya implementa `list`, `claim`, `fetch-spec`, `pick`, `status`, `heartbeat`, `transition`,
  `reassign` y `release`
- `flowctl/parser.py`
  ya expone subcomandos `gateway`
- `flow`
  ya orquesta wrappers de claim, plan y slices protegidas
- `docs/slave-remote-gateway-operator-runbook.md`
  ya documenta el modo manual y asistido

## Reglas de negocio

- el polling solo puede operar cuando `gateway.connection.mode=remote`
- el polling no puede correr si existe un `gateway_claim` local vigente para otra spec
- el polling no puede robar una spec ya reclamada por otro actor
- el polling debe usar exactamente el mismo contrato de elegibilidad que `pick`
- el polling debe parar al primer claim exitoso
- si el operator pide modo loop, debe existir un límite declarativo:
  - por iteraciones
  - por tiempo máximo
  - o por señal explícita de interrupción
- si el loop detecta errores repetidos de conectividad, debe entrar en backoff y terminar cuando
  supere el umbral configurado

## Modos permitidos en esta ola

### 1. Poll one-shot

Un intento único:

- lista trabajo elegible
- selecciona la primera spec elegible bajo el orden estable
- intenta `claim`
- si el claim gana, hace `fetch-spec`
- si no hay elegibles, devuelve `no-eligible-specs`

### 2. Watch loop acotado

Un loop controlado:

- repite `poll` cada cierto intervalo
- aplica backoff cuando no hay trabajo o hay errores transitorios
- se detiene en la primera spec reclamada
- se detiene por timeout, max attempts o señal del usuario

## Orden y elegibilidad

La selección automática debe respetar el orden ya gobernado:

- `state in {new, triaged}`
- luego `updated_at` ascendente
- luego `created_at` ascendente
- exclusión de specs con `assignee` distinto de null o del actor local si el claim sigue vigente

No se permite:

- reorder heurístico
- prioridad implícita por nombre
- selección aleatoria

## Algoritmo

### 1. `flow gateway poll`

1. Resolver configuración remota.
2. Validar que no exista claim local vigente para otra spec.
3. Pedir lista remota con filtros declarados.
4. Reusar la misma elegibilidad de `pick`.
5. Si no hay elegibles:
   - devolver `picked=false`
   - `reason=no-eligible-specs`
6. Si hay elegible:
   - intentar `claim`
   - si el claim falla por carrera recuperable, continuar con la siguiente elegible o terminar según
     política declarada
   - si el claim gana, ejecutar `fetch-spec`
   - devolver payload estructurado con `spec_id`, actor, lock, estado y fuente remota

### 2. `flow gateway watch`

1. Resolver actor, filtros, intervalo base, timeout y max attempts.
2. Repetir:
   - ejecutar `poll`
   - si `poll` reclama una spec:
     - imprimir resultado final
     - salir con código 0
   - si no reclama:
     - dormir con jitter leve
     - aplicar backoff si corresponde
3. Terminar con código controlado cuando:
   - se alcance timeout
   - se alcance max attempts
   - el usuario interrumpa
   - la conectividad supere el umbral de error fatal

### 3. Gestión de errores

- `SPEC_ALREADY_CLAIMED`
  - tratar como carrera recuperable, no como fatal inmediato
- error de conectividad transitorio
  - contar intento fallido, aplicar backoff
- claim local vigente para otra spec
  - abortar con error explícito
- gateway mal configurado
  - abortar sin loop

## Contrato CLI esperado

Se debe soportar al menos:

```bash
python3 ./flow gateway poll --actor <actor> [--state triaged] [--json]
python3 ./flow gateway watch --actor <actor> [--state triaged] [--interval-seconds 15] [--timeout-seconds 600] [--max-attempts 40] [--json]
```

Campos mínimos de salida JSON:

- `picked`
- `spec_id`
- `actor`
- `attempt`
- `attempts_total`
- `reason`
- `remote_state`
- `lock_token`
- `lock_expires_at`

## Safety Gates

La implementación debe cumplir:

- no correr en modo `master`
- no arrancar si existe claim local vigente para otra spec
- no mutar estado remoto salvo mediante `claim` y `fetch-spec`
- no ejecutar `plan`, `slice start`, `slice verify`, `release` ni `transition` automáticamente
- no persistir un daemon residente fuera de un comando explícito del operator

## Evidence Contract

La verificación debe mostrar:

- test unitario para `poll` sin elegibles
- test unitario para `poll` con claim exitoso
- test unitario para `watch` terminando por timeout o max attempts
- test unitario para `watch` deteniéndose al primer claim exitoso
- validación manual documentada en runbook con:
  - `poll` sin trabajo
  - `poll` con trabajo elegible
  - `watch` detenido al reclamar una spec

## Stop Conditions

Detener la implementación si ocurre cualquiera:

- la solución requiere endpoint nuevo del gateway para funcionar
- el loop necesita estado persistente adicional no contemplado por esta spec
- la solución introduce ejecución automática de SDLC más allá de `claim` y `fetch-spec`
- la verificación depende de timing frágil no controlable en tests

## Slices Propuestas

### Slice 1. Poll and watch CLI

- agregar `gateway poll`
- agregar `gateway watch`
- implementar loop con backoff acotado y salida estructurada
- tests de éxito, vacío, timeout y claim race

### Slice 2. Claim safety and local state gates

- impedir polling cuando exista claim local conflictivo
- unificar elegibilidad con `pick`
- endurecer mensajes de error y códigos de salida

### Slice 3. Runbook and operator docs

- actualizar runbook del `slave`
- documentar ejemplos de `poll` y `watch`
- aclarar límites de la autonomía permitida

## Slice Breakdown

```yaml
- name: poll-and-watch-cli
  targets:
    - ../../flow
    - ../../flowctl/gateway_ops.py
    - ../../flowctl/parser.py
    - ../../flowctl/test_gateway_ops.py
  hot_area: autonomous polling loop
  depends_on: []
  slice_mode: implementation-heavy
  surface_policy: required

- name: claim-safety-and-local-state-gates
  targets:
    - ../../flow
    - ../../flowctl/gateway_ops.py
    - ../../flowctl/test_gateway_ops.py
    - ../../workspace.config.json
  hot_area: polling safety gates
  depends_on:
    - poll-and-watch-cli
  slice_mode: implementation-heavy
  surface_policy: required

- name: runbook-and-operator-docs
  targets:
    - ../../docs/slave-remote-gateway-operator-runbook.md
    - ../../README.md
    - ../../specs/features/softos-slave-autonomous-intake-polling.spec.md
  hot_area: autonomous operator guidance
  depends_on:
    - claim-safety-and-local-state-gates
  slice_mode: implementation-heavy
  surface_policy: required
```

## Criterios de aceptacion

- existe `flow gateway poll` y devuelve salida estructurada cuando encuentra o no encuentra trabajo elegible
- existe `flow gateway watch` y se detiene al primer claim exitoso o al alcanzar sus límites declarados
- el loop autónomo no puede arrancar si el workspace ya tiene un claim local conflictivo
- la elegibilidad del polling coincide con la política ya gobernada por `pick`
- un claim exitoso materializa la spec canónica localmente
- la documentación del `slave` explica cómo usar `poll` y `watch` y qué límites de autonomía siguen vigentes

## Verification Matrix

```yaml
- name: autonomous-polling-unit
  level: custom
  command: python3 -m unittest flowctl.test_gateway_ops
  blocking_on:
    - ci
  environments:
    - local

- name: autonomous-polling-manual
  level: smoke
  command: |
    python3 ./flow gateway poll --actor dev-a --json
    python3 ./flow gateway watch --actor dev-a --interval-seconds 5 --timeout-seconds 30 --json
  blocking_on:
    - review
  environments:
    - local
```
