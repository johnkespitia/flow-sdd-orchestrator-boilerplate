---
schema_version: 3
name: "SoftOS slave remote operator ergonomics"
description: "Elevar la ergonomia operativa del workspace slave remoto con inspeccion rapida del claim, auto-heartbeat durante comandos largos y hooks controlados para publicar transitions automaticas desde hitos SDLC definidos."
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
  - ../../flowctl/features.py
  - ../../flowctl/test_gateway_ops.py
  - ../../docs/slave-remote-gateway-operator-runbook.md
  - ../../README.md
  - ../../specs/features/softos-slave-remote-operator-ergonomics.spec.md
---

# SoftOS slave remote operator ergonomics

## Objetivo

Reducir fricción operativa del developer que trabaja desde un workspace `slave` conectado a un
gateway remoto, agregando:

- una inspección rápida del claim local/remoto (`flow gateway status` o `flow gateway current`)
- renovación automática de heartbeat durante comandos largos protegidos
- publicación automática y controlada de `transition` desde hitos SDLC claramente mapeados

La meta es mejorar seguridad operativa y UX sin convertir todavía al `slave` en un worker autónomo.

## Contexto

La spec `softos-remote-intake-claim-and-slave-execution-bridge` ya dejó disponible el puente
base entre `flow` y el gateway remoto:

- `list`
- `claim`
- `fetch-spec`
- `heartbeat`
- `transition`
- `reassign`
- `release`

Eso resuelve el ciclo manual asistido, pero siguen faltando piezas para que el developer opere con
menos riesgo:

- hoy no existe una vista corta del claim activo sin inspeccionar `.flow/state/**`
- el heartbeat sigue siendo manual, por lo que el lock puede expirar durante comandos largos
- las transitions se publican manualmente y eso deja huecos entre el estado real del trabajo local y
  el registry remoto

La spec debe mejorar ergonomía, pero sin introducir selección automática de trabajo, polling, cola
ni cambios de ownership no gobernados.

## Foundations Aplicables

- `specs/000-foundation/spec-as-source-operating-model.spec.md`
- `specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md`
- `specs/000-foundation/repo-routing-and-worktree-orchestration.spec.md`
- `specs/features/softos-remote-intake-claim-and-slave-execution-bridge.spec.md`

## Domains Aplicables

- no aplica domain porque el cambio afecta tooling operativo del workspace y no agrega lenguaje
  estable de producto

## Governing Decision

- la fuente de verdad del ownership remoto sigue siendo el gateway
- el state local del `slave` sigue siendo derivado y auxiliar
- la automatización permitida en esta ola es ergonómica, no decisional
- ninguna automatización nueva puede seleccionar specs, tomar claims o reasignar ownership por sí sola

## Problema a resolver

El ciclo actual obliga al operator a recordar demasiado contexto manual:

- debe inferir si el claim local sigue vigente
- debe renovar heartbeat explícitamente aunque esté corriendo comandos legítimamente largos
- debe decidir y emitir transitions manuales aunque algunas puedan mapearse de forma estable desde
  hitos SDLC ya conocidos

Eso aumenta:

- expiración accidental del lock
- drift entre estado local y remoto
- dificultad de diagnóstico cuando un plan o ejecución falla por claim vencido

## Alcance

### Incluye

- comando CLI de inspección resumida del claim local/remoto
- auto-heartbeat durante comandos largos protegidos y solo cuando exista claim remoto vigente
- mapeo explícito de hitos SDLC a transitions automáticas permitidas
- actualización del runbook del operador `slave`

### No incluye

- `pick` automático o selección automática de trabajo
- polling continuo contra el gateway
- cola de trabajo del lado `slave`
- reasignación automática o elevación de privilegios
- transitions heurísticas o ambiguas no respaldadas por un mapeo explícito

## Repos afectados

| Repo | Targets |
| --- | --- |
| `sdd-workspace-boilerplate` | `../../flow`, `../../flowctl/gateway_ops.py`, `../../flowctl/parser.py`, `../../flowctl/features.py`, `../../flowctl/test_gateway_ops.py`, `../../docs/slave-remote-gateway-operator-runbook.md`, `../../README.md`, `../../specs/features/softos-slave-remote-operator-ergonomics.spec.md` |

## Resultado esperado

- el operator puede inspeccionar el claim actual con un solo comando
- los comandos largos protegidos mantienen vivo el lock sin intervención manual
- las transitions automáticas solo ocurren en hitos SDLC declarados y auditables
- la experiencia remota mejora sin introducir autonomía no gobernada

## Execution Surface Inventory

### Write paths obligatorios

- `flow`
- `flowctl/gateway_ops.py`
- `flowctl/parser.py`
- `flowctl/features.py`
- `flowctl/test_gateway_ops.py`
- `docs/slave-remote-gateway-operator-runbook.md`
- `README.md`

### Read paths obligatorios

- `.flow/state/<slug>.json`
- `workspace.config.json`
- `.env.gateway`
- `specs/features/softos-remote-intake-claim-and-slave-execution-bridge.spec.md`

### Out of scope explícito

- `gateway/app/**`
- endpoints nuevos para `pick`
- permisos/roles de reasignación
- scheduler o worker autónomo

## Technical Observed Inventory

Superficies existentes relevantes:

- `flowctl/gateway_ops.py`
  ya resuelve conexión remota, claim local, fetch de spec, heartbeat, transition, reassign y release
- `flowctl/features.py`
  hoy exige claim remoto vigente antes de `plan`
- `flowctl/parser.py`
  ya expone `flow gateway list|claim|fetch-spec|heartbeat|transition|reassign|release`
- `docs/slave-remote-gateway-operator-runbook.md`
  documenta el flujo manual actual

## Reglas de negocio

- `status/current` no puede mutar estado remoto; es estrictamente introspectivo
- el auto-heartbeat solo corre cuando:
  - el workspace está en `gateway.connection.mode=remote`
  - existe `gateway_claim` local completo
  - el comando ejecutado está dentro de la lista de comandos protegidos
- si el primer heartbeat automático falla por lock vencido o mismatch, el comando protegido debe
  abortar con error explícito; no debe continuar a ciegas
- las transitions automáticas deben ser opt-in por mapeo de hitos, no inferidas libremente
- los hitos mapeables en esta ola deben ser pocos y deterministas

## Hitos SDLC permitidos para transition automática

La implementación solo puede considerar estos mapeos iniciales:

| Hito local | Transition remota |
| --- | --- |
| `flow plan <slug>` exitoso en `slave` con claim vigente | `triaged` |
| `flow slice start <slug> <slice>` exitoso en `slave` con claim vigente | `in_edit` |
| `flow slice verify <slug> <slice>` exitoso cuando la slice queda verificada | `in_review` |

Reglas:

- si el estado remoto actual no acepta esa transition, el sistema debe registrar el fallo y dejar
  el comando principal decidir si aborta o continúa según el contrato local
- esta spec no autoriza transitions automáticas hacia `approved`, `released`, `done` o equivalentes

## Algoritmo

### 1. `flow gateway status|current`

1. Resolver `gateway.connection`.
2. Leer `gateway_claim` local si existe.
3. Si no existe claim local, devolver estado local vacío y finalizar sin error.
4. Si existe claim local, consultar el spec remoto correspondiente.
5. Comparar:
   - `actor`
   - `lock_token`
   - `assignee`
   - `lock_expires_at`
   - `state`
6. Imprimir salida resumida y JSON opcional con:
   - claim local
   - estado remoto
   - `claim_matches_remote=true|false`
   - motivo de mismatch si aplica

### 2. Auto-heartbeat

1. Antes de ejecutar un comando protegido, resolver si existe claim remoto local completo.
2. Si no existe, no arrancar heartbeat loop.
3. Si existe, iniciar un loop de heartbeat con intervalo conservador menor al TTL.
4. Ejecutar el comando principal.
5. Mientras el comando siga vivo:
   - enviar heartbeat
   - registrar último `lock_expires_at`
   - detenerse al primer `LOCK_MISMATCH`, expiración o error fatal de conectividad configurado como blocking
6. Al terminar el comando principal, detener el loop y propagar el resultado real del comando.

### 3. Transition automática por hook

1. El comando protegido termina exitosamente.
2. Resolver si el hito tiene transition mapeada.
3. Verificar claim remoto vigente.
4. Intentar `transition`.
5. Si la transition es válida:
   - registrar salida/auditoría local
6. Si la transition falla por estado remoto inválido:
   - reportar la falla
   - no inventar un estado alterno

## Disposition And Error Matrix

| Caso | Disposición |
| --- | --- |
| No hay `gateway_claim` local | `status/current` responde vacío; auto-heartbeat y auto-transition no activan |
| Claim local existe pero el remoto no coincide | `status/current` marca mismatch; comandos protegidos fallan antes de operar |
| Heartbeat automático recibe `LOCK_MISMATCH` | abortar el comando protegido |
| Heartbeat automático recibe error transitorio de red | reintento limitado; si supera umbral, abortar |
| Transition automática inválida | no mutar estado local; reportar error explícito |
| Workspace no está en modo `remote` | las funciones nuevas quedan inertizadas |

## Thresholds

- el heartbeat loop no debe enviar heartbeats más frecuentes que cada 30 segundos
- el intervalo por defecto debe ser configurable, pero nunca mayor al 50% del TTL vigente
- máximo 2 reintentos transitorios por ciclo antes de abortar

## Stop Conditions

La implementación debe detenerse y no expandirse a:

- selección automática de specs
- pick heurístico
- polling continuo
- control de permisos de reasignación
- transitions automáticas no listadas en esta spec

## Evidence Package

- tests unitarios para `status/current`
- tests unitarios para auto-heartbeat con claim válido y con mismatch
- tests unitarios o de integración para hooks de transition mapeados
- evidencia documental del flujo actualizado del operador `slave`
- smoke reproducible con:
  - claim
  - comando protegido
  - heartbeat automático observado
  - transition automática observada o fallo explícito controlado

## Evidence Delivery Contract

- tests en `flowctl/test_gateway_ops.py`
- comandos y flujo esperado documentados en `docs/slave-remote-gateway-operator-runbook.md`
- si hay smoke manual, debe quedar descrito con comandos exactos en docs

## Slice Breakdown

```yaml
- name: remote-claim-status-introspection
  targets:
    - ../../flow
    - ../../flowctl/gateway_ops.py
    - ../../flowctl/parser.py
    - ../../flowctl/test_gateway_ops.py
  hot_area: claim inspection surface
  depends_on: []
  slice_mode: implementation-heavy
  surface_policy: required

- name: protected-command-auto-heartbeat
  targets:
    - ../../flow
    - ../../flowctl/gateway_ops.py
    - ../../flowctl/features.py
    - ../../flowctl/test_gateway_ops.py
  hot_area: long-running command protection
  depends_on:
    - remote-claim-status-introspection
  slice_mode: implementation-heavy
  surface_policy: required

- name: sdlc-transition-hooks-and-runbook
  targets:
    - ../../flow
    - ../../flowctl/gateway_ops.py
    - ../../flowctl/features.py
    - ../../flowctl/parser.py
    - ../../docs/slave-remote-gateway-operator-runbook.md
    - ../../README.md
  hot_area: transition hook orchestration
  depends_on:
    - protected-command-auto-heartbeat
  slice_mode: implementation-heavy
  surface_policy: required
```

## Criterios de aceptacion

- existe `flow gateway status` o `flow gateway current` y muestra claim local/remoto de forma resumida
- el comando nuevo indica claramente si el claim local coincide o no con el remoto
- los comandos largos protegidos pueden renovar heartbeat automáticamente con claim vigente
- si el lock deja de ser válido durante el loop, el comando protegido falla de forma explícita
- las transitions automáticas solo se disparan desde hitos SDLC definidos en esta spec
- el runbook del `slave` documenta el nuevo comportamiento y sus límites

## Verification Matrix

```yaml
- name: slave-ergonomics-unit
  level: custom
  command: python3 -m unittest flowctl.test_gateway_ops
  blocking_on:
    - ci
  environments:
    - local
  notes: valida introspeccion del claim, auto-heartbeat y hooks de transition

- name: slave-ergonomics-smoke
  level: integration
  command: python3 ./flow gateway status --json
  blocking_on:
    - ci
  environments:
    - local
  notes: valida que el operator pueda inspeccionar claim remoto y ejecutar el flujo actualizado
```

## Test plan

- ampliar `flowctl/test_gateway_ops.py`
- smoke sobre workspace `slave` conectado a gateway local o remoto de prueba

## Rollout

- introducir primero introspección de claim
- luego auto-heartbeat en comandos protegidos
- luego hooks de transition y documentación

## Rollback

- si el auto-heartbeat resulta inestable, puede deshabilitarse manteniendo el comando de status
- los hooks de transition pueden revertirse sin romper el bridge manual existente
