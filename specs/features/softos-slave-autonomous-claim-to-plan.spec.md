---
schema_version: 3
name: "SoftOS slave autonomous claim to plan"
description: "Permitir que un workspace slave, de forma opt-in y gobernada, ejecute `flow plan` automáticamente después de ganar un claim remoto y materializar la spec canónica, sin avanzar todavía a `slice start`, `slice verify`, `release` ni cierre autónomo."
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
  - specs/features/softos-slave-autonomous-intake-polling.spec.md
required_runtimes: []
required_services: []
required_capabilities: []
stack_projects: []
stack_services: []
stack_capabilities: []
targets:
  - ../../flow
  - ../../flowctl/gateway_ops.py
  - ../../flowctl/features.py
  - ../../flowctl/parser.py
  - ../../flowctl/test_gateway_ops.py
  - ../../docs/slave-remote-gateway-operator-runbook.md
  - ../../README.md
  - ../../workspace.config.json
  - ../../specs/features/softos-slave-autonomous-claim-to-plan.spec.md
---

# SoftOS slave autonomous claim to plan

## Objetivo

Habilitar la siguiente ola de autonomía razonable para workspaces `slave` conectados a un gateway
remoto:

- descubrir una spec elegible
- ganar `claim` remoto de forma auditable
- materializar localmente la spec canónica
- ejecutar `flow plan <slug>` automáticamente bajo un gate explícito
- detenerse inmediatamente después del plan

La feature debe reducir latencia operativa después del `claim`, pero sin convertir todavía al
`slave` en un ejecutor autónomo de slices o de release.

## Contexto

Las olas previas ya dejaron cerrado el tramo necesario para intake y ownership:

- el bridge remoto soporta `list`, `claim`, `fetch-spec`, `heartbeat`, `transition`, `reassign` y
  `release`
- `pick`, `poll` y `watch` ya pueden encontrar una spec elegible y reclamarla de forma auditable
- `flow plan` en modo `slave` ya exige claim remoto vigente
- los comandos protegidos ya cuentan con auto-heartbeat y hooks de transition controlados

La frontera actual es intencional:

- la autonomía puede descubrir trabajo y apropiárselo
- la ejecución del SDLC sigue requiriendo intención explícita del humano o del agente operador

La siguiente ola razonable no es autonomía completa de workflow, sino permitir que el mismo proceso
que ganó el `claim` llegue hasta `plan` y se detenga allí.

## Foundations Aplicables

- `spec-as-source-operating-model`
  la spec canónica remota sigue siendo la fuente de verdad; el plan debe nacer de esa spec y no de
  una copia local divergente
- `spec-driven-delivery-and-infrastructure`
  la automatización no puede saltarse gates del SDLC ni inventar avance de slices
- `repo-routing-and-worktree-orchestration`
  el `plan` producido debe seguir el mismo routing y contratos de worktree/slices que un `plan`
  lanzado manualmente

## Domains Aplicables

- no aplica domain porque la feature es de orquestación operativa del workspace

## Governing Decision

- la autonomía permitida en esta ola termina en `plan`
- `claim -> fetch-spec -> plan` debe ser opt-in y explícito; nunca implícito por default
- `slice start`, `slice verify`, `workflow execute-feature`, `release` y cierres de workflow siguen
  fuera de la autonomía permitida
- el gateway sigue siendo la fuente de verdad del ownership remoto
- cualquier fallo después del `claim` debe ser observable y no debe ocultar el estado real del lock

## Problema a resolver

Con `poll` o `watch`, el workspace ya puede llegar automáticamente hasta un `claim` exitoso, pero
el operador todavía debe intervenir de inmediato para disparar `flow plan`.

Eso deja una brecha operativa innecesaria:

- el proceso que ya resolvió elegibilidad y ownership debe esperar otra intención explícita
- la ventana entre `claim` y `plan` introduce latencia y coordinación manual sin valor adicional
- un agente operador no tiene todavía un punto medio entre asistencia y ejecución total del SDLC

La spec debe cerrar esa brecha sin abrir todavía decisiones autónomas de implementación.

## Alcance

### Incluye

- gate explícito para habilitar auto-plan después de `claim`
- integración de ese gate en `flow gateway poll` y `flow gateway watch`, o equivalente funcional
- ejecución automática de `flow plan <slug>` solo después de:
  - `claim` exitoso
  - `fetch-spec` exitoso
  - validación de claim remoto vigente
- reutilización del auto-heartbeat ya existente durante el `plan`
- salida estructurada que distinga:
  - claim exitoso sin auto-plan
  - claim exitoso con plan exitoso
  - claim exitoso con plan fallido
- documentación operativa del modo `claim -> plan`

### No incluye

- arranque automático de slices
- verificación automática de slices
- `workflow execute-feature --start-slices`
- `release`, `promote`, `verify` o cierre automático
- retries automáticos ilimitados de `plan`
- heurísticas para decidir si una spec "merece" plan automático
- callbacks remotos nuevos de engine por etapa completa

## Repos afectados

| Repo | Targets |
| --- | --- |
| `sdd-workspace-boilerplate` | `../../flow`, `../../flowctl/gateway_ops.py`, `../../flowctl/features.py`, `../../flowctl/parser.py`, `../../flowctl/test_gateway_ops.py`, `../../docs/slave-remote-gateway-operator-runbook.md`, `../../README.md`, `../../workspace.config.json`, `../../specs/features/softos-slave-autonomous-claim-to-plan.spec.md` |

## Resultado esperado

- el operator puede dejar un `slave` esperando trabajo y, cuando gane una spec, obtener también el
  plan local sin un segundo comando manual
- el comportamiento anterior de `poll` y `watch` se preserva cuando el gate de auto-plan está
  apagado
- el `plan` automático usa exactamente la misma spec canónica y los mismos guardrails que el
  `plan` manual
- el sistema se detiene antes de cualquier decisión autónoma de implementación
- un fallo de `plan` no deja ambigüedad sobre si el claim remoto sigue vivo o no

## Execution Surface Inventory

### Write paths obligatorios

- `flow`
- `flowctl/gateway_ops.py`
- `flowctl/features.py`
- `flowctl/parser.py`
- `flowctl/test_gateway_ops.py`
- `docs/slave-remote-gateway-operator-runbook.md`
- `README.md`
- `workspace.config.json`

### Read paths obligatorios

- `.flow/state/<slug>.json`
- `.env.gateway`
- `workspace.config.json`
- `specs/features/softos-remote-intake-claim-and-slave-execution-bridge.spec.md`
- `specs/features/softos-slave-remote-operator-ergonomics.spec.md`
- `specs/features/softos-slave-remote-governance-and-assisted-picking.spec.md`
- `specs/features/softos-slave-autonomous-intake-polling.spec.md`

### Out of scope explícito

- `gateway/app/**`
- daemon autónomo de largo ciclo que sobreviva fuera del comando invocado por el operator
- planificación de más de una spec en la misma sesión automática
- ejecución automática de slices después del plan
- auto-release ante fallo o éxito de `plan`
- scoring, fairness o scheduling global entre múltiples workers

## Technical Observed Inventory

Superficies existentes que esta ola debe reutilizar y no reimplementar:

- `flowctl/gateway_ops.py`
  ya resuelve `pick`, `poll`, `watch`, `claim`, `fetch-spec`, `heartbeat` y `transition`
- `flowctl/features.py`
  ya valida claim remoto antes de `plan`
- `flow`
  ya envuelve `plan` con guards y transitions automáticas permitidas
- `docs/slave-remote-gateway-operator-runbook.md`
  ya documenta el flujo manual, asistido y de polling acotado

## Policy Gate

La autonomía `claim -> plan` debe quedar apagada por defecto.

Se permite habilitarla solo mediante al menos uno de estos mecanismos explícitos:

- flag por invocación, por ejemplo `flow gateway poll --auto-plan`
- flag por invocación, por ejemplo `flow gateway watch --auto-plan`
- configuración declarativa tipo `gateway.execution.auto_plan=true` en `workspace.config.json`

Reglas:

- si no hay gate explícito, `poll` y `watch` deben preservar exactamente el comportamiento actual
- un flag por CLI prevalece sobre el default del workspace
- el gate solo tiene efecto cuando el comando gana un `claim`; no debe lanzar `plan` sobre una spec
  ya reclamada en otra sesión

## Reglas de negocio

- el auto-plan solo puede iniciar después de `claim` exitoso y `fetch-spec` exitoso
- el auto-plan debe ejecutar exactamente un `flow plan <slug>` por spec reclamada
- el auto-plan no puede encadenar `slice start` ni ningún otro paso del SDLC
- si `plan` termina exitosamente, la ola termina ahí y devuelve control al operator
- si `plan` falla, el sistema debe devolver error estructurado y dejar explícito si el `claim`
  remoto sigue vigente
- un fallo de `plan` no debe detonar `release` automático
- la transition remota permitida por `plan` exitoso sigue siendo únicamente la ya gobernada:
  `triaged`
- no se autorizan transitions automáticas nuevas por fallo de `plan`
- si el workspace ya tiene un `gateway_claim` local vigente antes de arrancar `poll/watch`, el
  comando debe seguir fallando como hoy

## Actor y modo operativo

| Actor lógico | Acción permitida en esta ola |
| --- | --- |
| humano operator | iniciar `poll` o `watch` con o sin `--auto-plan` |
| agente operator | iniciar `poll` o `watch` con o sin `--auto-plan` |
| proceso autónomo derivado del comando | reclamar una sola spec y ejecutar un solo `plan` |

No se autoriza:

- que el proceso vuelva a entrar en loop después de un `plan` exitoso
- que el proceso tome una segunda spec en la misma ejecución tras un `plan` fallido
- que el proceso decida por sí mismo seguir a slices

## Flujo principal

### 1. `poll --auto-plan`

1. Resolver `gateway.connection.mode=remote`.
2. Verificar que no exista `gateway_claim` local vigente.
3. Ejecutar el mismo algoritmo de elegibilidad y claim que `poll`.
4. Si no hay spec elegible:
   - devolver `no-eligible-specs`
5. Si el claim falla por carrera:
   - devolver conflicto y finalizar sin reintentar otra spec en la misma invocación
6. Si el claim gana:
   - ejecutar `fetch-spec`
   - verificar claim remoto vigente
   - ejecutar `flow plan <slug>`
7. Si `plan` termina OK:
   - devolver resultado combinado de `claim`, `fetch-spec` y `plan`
8. Si `plan` falla:
   - devolver `plan_failed_after_claim`
   - preservar evidencia de claim vigente o mismatch

### 2. `watch --auto-plan`

1. Resolver `gateway.connection.mode=remote`.
2. Verificar que no exista `gateway_claim` local vigente.
3. Repetir el loop actual de `watch` hasta ganar un `claim` o agotar límites.
4. Si el loop termina sin claim:
   - devolver el mismo resultado actual de timeout/max-attempts/no-eligible
5. Si el loop gana un `claim`:
   - detener el loop
   - ejecutar `fetch-spec`
   - verificar claim remoto vigente
   - ejecutar exactamente un `flow plan <slug>`
6. Si `plan` termina OK:
   - devolver control al operator sin reanudar el loop
7. Si `plan` falla:
   - devolver error estructurado sin reanudar el loop

## Algoritmo detallado

### 1. Resolución del gate

1. Resolver flags de CLI y configuración de workspace.
2. Computar `auto_plan_enabled=true|false`.
3. Registrar en salida y logs qué fuente habilitó o deshabilitó el gate.

### 2. Claim and fetch

1. Ejecutar `poll` o `watch` usando exactamente el contrato existente.
2. Si no hubo claim exitoso, no invocar `plan`.
3. Si hubo claim exitoso, materializar o refrescar la spec local con `fetch-spec`.
4. Confirmar que el slug local resultante sea el que usará `flow plan`.

### 3. Verificación previa al plan

1. Leer `gateway_claim` local recién persistido.
2. Consultar el estado remoto o validar token vigente mediante la ruta ya existente.
3. Si hay mismatch, expiración o lock perdido:
   - abortar antes de lanzar `plan`
   - devolver `claim_not_valid_for_plan`

### 4. Ejecución de plan

1. Iniciar `flow plan <slug>` con el mismo wrapper protegido ya usado para `plan` manual.
2. Mantener auto-heartbeat mientras el comando siga vivo.
3. Permitir únicamente las transitions automáticas ya autorizadas por la spec de ergonomía.
4. Al finalizar:
   - si sale `0`, marcar `plan_status=passed`
   - si sale distinto de `0`, marcar `plan_status=failed`

### 5. Cierre del comando

1. Emitir salida estructurada final con:
   - `spec_id`
   - `slug`
   - `claim_status`
   - `plan_attempted`
   - `plan_status`
   - `remote_claim_still_valid`
   - `auto_plan_enabled`
   - `auto_plan_source`
2. Finalizar sin arrancar ninguna otra etapa del SDLC.

## Disposition And Error Matrix

| Caso | Disposición |
| --- | --- |
| `auto_plan` apagado | preservar comportamiento actual de `poll/watch` |
| no hay spec elegible | devolver `no-eligible-specs`; no ejecutar `plan` |
| claim pierde por carrera | devolver conflicto; no intentar segunda spec en la misma ejecución |
| `fetch-spec` falla después del claim | devolver `fetch_failed_after_claim`; no ejecutar `plan` |
| claim válido localmente pero remoto expiró antes del plan | devolver `claim_not_valid_for_plan`; no ejecutar `plan` |
| `plan` falla por error propio del plan | devolver `plan_failed_after_claim`; no liberar lock automáticamente |
| auto-heartbeat detecta `LOCK_MISMATCH` durante `plan` | abortar `plan`; devolver claim inválido |
| `watch` alcanza timeout o max attempts | preservar comportamiento actual; no ejecutar `plan` |
| `plan` exitoso | detener flujo y devolver resultado combinado; no seguir a slices |

## Thresholds

- `auto_plan` debe intentar `plan` una sola vez por claim exitoso
- `watch --auto-plan` no puede reanudar polling después de un `plan` exitoso o fallido
- no se permite fallback automático a otra spec tras fallo de `fetch-spec` o `plan`
- el heartbeat durante `plan` mantiene los umbrales ya declarados por la spec de ergonomía
- la salida final debe permitir distinguir claramente entre:
  - fallo antes de ganar claim
  - fallo después de claim pero antes de plan
  - fallo durante plan

## Evidence Contract

Para aprobar implementación de esta spec debe existir evidencia de:

- compatibilidad hacia atrás:
  `poll/watch` sin gate explícito preservan el comportamiento actual
- activación explícita:
  `poll/watch` con gate habilitado ejecutan `plan` exactamente una vez
- stop boundary:
  un `plan` exitoso no dispara `slice start` ni workflow completo
- error boundary:
  un fallo de `plan` no detona `release` automático ni retry hacia otra spec

Artefactos mínimos:

- pruebas unitarias/contractuales en `flowctl/test_gateway_ops.py`
- documentación actualizada en `docs/slave-remote-gateway-operator-runbook.md`
- ejemplo de uso en `README.md`

## Verification Matrix

```yaml
- name: spec-review-autonomous-claim-to-plan
  level: custom
  command: python3 ./flow spec review specs/features/softos-slave-autonomous-claim-to-plan.spec.md
  blocking_on:
    - approval
  environments:
    - local
  notes: valida estructura, targets, slices y contratos de la spec

- name: spec-ci-autonomous-claim-to-plan
  level: custom
  command: python3 ./flow ci spec specs/features/softos-slave-autonomous-claim-to-plan.spec.md
  blocking_on:
    - approval
  environments:
    - local
  notes: valida formato de gobernanza y readiness del documento

- name: gateway-auto-plan-unit
  level: custom
  command: python3 -m unittest flowctl.test_gateway_ops flowctl.test_flow_gateway_autoplan
  blocking_on:
    - ci
  environments:
    - local
  notes: valida gate auto-plan, frontera de stop y cableado entre `flow` y `gateway_ops`
```

## Acceptance Criteria

- existe un gate explícito para habilitar `claim -> plan` y está apagado por defecto
- `flow gateway poll` y/o `watch` pueden, con ese gate, ejecutar `plan` automáticamente después de
  claim y fetch exitosos
- el plan automático usa los mismos guardrails de claim remoto y auto-heartbeat que el plan manual
- el flujo automático se detiene exactamente después de `plan`
- un fallo de `plan` no se convierte en slices automáticas, retry hacia otra spec ni release
  automático
- la salida estructurada permite saber si el claim se obtuvo, si el plan corrió y si el claim
  siguió vigente al cerrar

## Slice Breakdown

```yaml
- name: auto-plan-policy-and-cli-contract
  targets:
    - ../../flow
    - ../../flowctl/parser.py
    - ../../workspace.config.json
    - ../../README.md
    - ../../specs/features/softos-slave-autonomous-claim-to-plan.spec.md
  hot_area: gateway auto-plan gate
  depends_on: []
  slice_mode: governance
  surface_policy: required
  minimum_valid_completion: el gate explícito queda definido y el comportamiento backward-compatible queda documentado
  validated_noop_allowed: false
  acceptable_evidence:
    - contrato CLI/config documentado en spec
    - revisión de compatibilidad hacia atrás

- name: claim-fetch-plan-execution-wrapper
  targets:
    - ../../flow
    - ../../flowctl/gateway_ops.py
    - ../../flowctl/features.py
    - ../../flowctl/test_gateway_ops.py
  hot_area: autonomous plan boundary
  depends_on:
    - auto-plan-policy-and-cli-contract
  slice_mode: implementation-heavy
  surface_policy: required

- name: docs-and-operator-evidence
  targets:
    - ../../docs/slave-remote-gateway-operator-runbook.md
    - ../../README.md
    - ../../specs/features/softos-slave-autonomous-claim-to-plan.spec.md
  hot_area: operator runbook
  depends_on:
    - claim-fetch-plan-execution-wrapper
  slice_mode: minimal-change
  surface_policy: required
  minimum_valid_completion: runbook y README explican el gate, los límites y los resultados esperados
  validated_noop_allowed: false
  acceptable_evidence:
    - ejemplos reproducibles de `poll/watch --auto-plan`
    - límites explícitos respecto a slices y release
```
