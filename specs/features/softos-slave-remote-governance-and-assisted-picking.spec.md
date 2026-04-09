---
schema_version: 3
name: "SoftOS slave remote governance and assisted picking"
description: "Definir la gobernanza del ownership remoto del slave para reasignacion autorizada, seleccion asistida tipo flow gateway pick y evolucion futura hacia polling/cola con gates y stop conditions explicitos."
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
  - ../../flowctl/test_gateway_ops.py
  - ../../gateway/app/main.py
  - ../../gateway/app/models.py
  - ../../gateway/app/store.py
  - ../../gateway/tests/test_remote_spec_bridge_api.py
  - ../../docs/slave-remote-gateway-operator-runbook.md
  - ../../docs/spec-registry-state-contract.md
  - ../../README.md
  - ../../workspace.config.json
  - ../../specs/features/softos-slave-remote-governance-and-assisted-picking.spec.md
---

# SoftOS slave remote governance and assisted picking

## Objetivo

Cerrar la gobernanza del ownership remoto para workspaces `slave` y preparar una selección asistida
de trabajo más segura, definiendo:

- reasignación autorizada con roles, motivo y modo `force`
- `flow gateway pick` como selección asistida, no automática
- una frontera explícita entre asistencia y autonomía futura por polling/cola

## Contexto

El bridge remoto actual ya soporta:

- `claim` exclusivo
- `reassign` explícito
- `release`
- `transition`

Pero la política actual todavía es débil en dos frentes:

- la reasignación no está modelada todavía con roles/admins y autorización explícita
- no existe una ayuda segura para elegir una spec disponible sin exigir al operator leer primero el
  listado completo y decidir manualmente cada vez

Además, aparece la tentación de ir directo a polling o cola, pero eso sería peligroso si todavía no
está cerrada la gobernanza del ownership.

## Foundations Aplicables

- `specs/000-foundation/spec-as-source-operating-model.spec.md`
- `specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md`
- `specs/000-foundation/repo-routing-and-worktree-orchestration.spec.md`
- `specs/features/softos-remote-intake-claim-and-slave-execution-bridge.spec.md`

## Domains Aplicables

- no aplica domain porque el cambio afecta orquestación y permisos operativos del workspace

## Governing Decision

- la reasignación debe pasar de ser solo explícita a ser explícita y autorizada
- `pick` en esta ola será asistido y sin background loop
- polling/cola quedan diferidos hasta que:
  - permisos de ownership estén cerrados
  - auto-heartbeat exista
  - transitions automáticas estén gobernadas

## Problema a resolver

Sin gobernanza explícita:

- cualquier reasignación futura corre el riesgo de ser inconsistente o poco auditable
- una ayuda de selección mal diseñada puede provocar carreras o claims inesperados
- avanzar a polling/cola sin política de ownership cerrada produciría trabajo autónomo con
  ambigüedad operativa

## Alcance

### Incluye

- política explícita de reasignación autorizada
- contrato API/CLI para reasignación con motivo y modo `force`
- `flow gateway pick` como helper asistido para encontrar una spec elegible y reclamarla
- definición de gates y stop conditions para una futura ola de polling/cola

### No incluye

- implementación de worker autónomo continuo
- ejecución automática de specs desde cola
- decisiones automáticas de priorización no trazables
- integración con sistemas externos de RBAC empresariales

## Repos afectados

| Repo | Targets |
| --- | --- |
| `sdd-workspace-boilerplate` | `../../flow`, `../../flowctl/gateway_ops.py`, `../../flowctl/parser.py`, `../../flowctl/test_gateway_ops.py`, `../../gateway/app/main.py`, `../../gateway/app/models.py`, `../../gateway/app/store.py`, `../../gateway/tests/test_remote_spec_bridge_api.py`, `../../docs/slave-remote-gateway-operator-runbook.md`, `../../docs/spec-registry-state-contract.md`, `../../README.md`, `../../workspace.config.json`, `../../specs/features/softos-slave-remote-governance-and-assisted-picking.spec.md` |

## Resultado esperado

- la reasignación remota tiene política clara de quién puede hacerla y bajo qué condiciones
- `flow gateway pick` ayuda a elegir trabajo disponible, pero no toma decisiones autónomas opacas
- la evolución a polling/cola queda documentada como ola posterior con gates obligatorios

## Execution Surface Inventory

### Write paths obligatorios

- `gateway/app/main.py`
- `gateway/app/models.py`
- `gateway/app/store.py`
- `gateway/tests/test_remote_spec_bridge_api.py`
- `flow`
- `flowctl/gateway_ops.py`
- `flowctl/parser.py`
- `flowctl/test_gateway_ops.py`
- `docs/spec-registry-state-contract.md`
- `docs/slave-remote-gateway-operator-runbook.md`
- `README.md`
- `workspace.config.json`

### Read paths obligatorios

- `.flow/state/<slug>.json`
- `workspace.config.json`
- `.env.gateway`
- `specs/features/softos-remote-intake-claim-and-slave-execution-bridge.spec.md`
- `docs/softos-recovery-playbook.md`

### Out of scope explícito

- daemon de polling permanente
- ejecución automática de plan/slices tras `pick`
- multi-tenant RBAC externo
- políticas de scheduling complejas basadas en scoring dinámico

## Roles y autorización

Roles mínimos permitidos por esta spec:

| Rol | Capacidades |
| --- | --- |
| `assignee` | puede liberar su claim y solicitar transferencia |
| `coordinator` | puede reasignar entre actors con motivo obligatorio |
| `admin` | puede forzar reasignación y resolver locks conflictivos |

Fuente inicial de rol:

- `workspace.config.json`
- variables o configuración local mínima del actor

No es necesario introducir un proveedor externo de identidad en esta ola.

## Reglas de negocio

- el actor actual no puede reasignar silenciosamente a otro actor sin motivo registrado
- `force=true` solo puede usarse por `admin`
- `pick` no puede saltarse el contrato de `claim`; siempre termina en un `claim` explícito y auditable
- `pick` debe ser deterministicamente acotado por filtros y orden declarado
- si no hay una spec elegible, `pick` debe responder sin mutación
- polling/cola no pueden implementarse en esta ola, solo especificarse con gates

## Assisted Picking Rules

`flow gateway pick` debe funcionar así:

1. listar specs remotas elegibles bajo filtros explícitos
2. seleccionar la primera elegible según un orden estable
3. mostrar cuál fue elegida y por qué
4. ejecutar `claim`
5. materializar la spec canónica localmente

Orden estable permitido en esta ola:

- primero `state in {new, triaged}`
- luego `updated_at` ascendente o `created_at` ascendente
- exclusión de specs ya asignadas a otro actor con lock vigente

No se permite:

- scoring heurístico opaco
- round-robin multi-worker
- prioridad basada en señales externas no trazadas

## Algoritmo

### 1. Reasignación autorizada

1. Resolver actor solicitante y rol operativo.
2. Cargar estado remoto de la spec.
3. Validar si el actor solicitante está autorizado para:
   - transferencia normal
   - `force`
4. Exigir `reason` no vacío.
5. Ejecutar reasignación remota.
6. Rotar `lock_token`.
7. Auditar:
   - actor solicitante
   - actor origen
   - actor destino
   - motivo
   - uso de `force`

### 2. `flow gateway pick`

1. Resolver modo `remote`.
2. Consultar lista remota con filtros explícitos.
3. Eliminar specs no elegibles.
4. Ordenar de forma estable.
5. Si no queda ninguna:
   - devolver `no-eligible-specs`
6. Si queda una:
   - mostrar spec candidata
   - ejecutar `claim`
   - ejecutar `fetch-spec`
   - devolver claim resultante

### 3. Gates para polling/cola futura

Antes de permitir polling o cola deben existir, y ser verificables:

- política de roles y force ya implementada
- `pick` asistido validado en producción controlada
- auto-heartbeat disponible
- transitions automáticas gobernadas
- evidencia de que el ownership remoto no deja ambigüedad residual

## Authorization Matrix

| Acción | assignee | coordinator | admin |
| --- | --- | --- | --- |
| `release` propio | sí | sí | sí |
| `reassign` sin force | no directo; solo solicitud | sí | sí |
| `reassign` con `force=true` | no | no | sí |
| `pick` | sí | sí | sí |
| iniciar polling/cola | no | no | no en esta ola |

## Disposition And Error Matrix

| Caso | Disposición |
| --- | --- |
| actor sin rol suficiente para `reassign` | `403` o error equivalente con código explícito |
| `reason` vacío en reasignación | rechazar |
| `force=true` sin rol `admin` | rechazar |
| `pick` sin specs elegibles | respuesta vacía sin mutación |
| `pick` encuentra spec pero el claim falla por carrera | devolver conflicto y no intentar una segunda sin orden explícito |
| polling/cola solicitado en esta ola | bloquear por spec y documentación |

## Stop Conditions

La implementación debe detenerse y no extenderse a:

- worker autónomo residente
- retries implícitos de `pick` sobre múltiples specs sin informar al operator
- prioridad dinámica no declarada
- bypass de autorización en reasignación

## Evidence Package

- tests del gateway para autorización y auditoría de reasignación
- tests del CLI para `pick`
- documentación del contrato de roles y de la diferencia entre `pick` asistido y polling/cola
- smoke reproducible:
  - actor no autorizado intenta reasignar y falla
  - coordinator o admin reasigna con motivo
  - `pick` reclama una spec elegible y la materializa

## Evidence Delivery Contract

- `gateway/tests/test_remote_spec_bridge_api.py`
- `flowctl/test_gateway_ops.py`
- `docs/spec-registry-state-contract.md`
- `docs/slave-remote-gateway-operator-runbook.md`

## Slice Breakdown

```yaml
- name: authorized-reassignment-policy
  targets:
    - ../../gateway/app/main.py
    - ../../gateway/app/models.py
    - ../../gateway/app/store.py
    - ../../gateway/tests/test_remote_spec_bridge_api.py
    - ../../docs/spec-registry-state-contract.md
  hot_area: remote ownership authorization
  depends_on: []
  slice_mode: implementation-heavy
  surface_policy: required

- name: assisted-pick-cli
  targets:
    - ../../flow
    - ../../flowctl/gateway_ops.py
    - ../../flowctl/parser.py
    - ../../flowctl/test_gateway_ops.py
    - ../../docs/slave-remote-gateway-operator-runbook.md
  hot_area: assisted intake selection
  depends_on:
    - authorized-reassignment-policy
  slice_mode: implementation-heavy
  surface_policy: required

- name: future-autonomy-gates-and-docs
  targets:
    - ../../README.md
    - ../../workspace.config.json
    - ../../docs/slave-remote-gateway-operator-runbook.md
    - ../../docs/spec-registry-state-contract.md
  hot_area: polling queue governance
  depends_on:
    - assisted-pick-cli
  slice_mode: implementation-heavy
  surface_policy: required
```

## Criterios de aceptacion

- la reasignación autorizada define roles, permisos, auditoría y modo `force`
- el gateway rechaza reasignaciones no autorizadas o sin motivo
- `flow gateway pick` queda definido como selección asistida con reglas explícitas y orden estable
- `pick` no introduce autonomía opaca ni ejecuta trabajo más allá de claim/fetch local
- la evolución a polling/cola queda separada por gates y stop conditions verificables

## Verification Matrix

```yaml
- name: governance-and-pick-api-contract
  level: integration
  command: python3 -m unittest gateway.tests.test_remote_spec_bridge_api
  blocking_on:
    - ci
  environments:
    - local
  notes: valida permisos, auditoria de reasignacion y contrato del gateway

- name: governance-and-pick-cli
  level: custom
  command: python3 -m unittest flowctl.test_gateway_ops
  blocking_on:
    - ci
  environments:
    - local
  notes: valida comportamiento de pick y reglas del cliente flow
```

## Test plan

- ampliar tests del gateway para autorización y `force`
- ampliar tests del CLI para `pick`
- smoke manual controlado con dos actores y una spec elegible

## Rollout

- introducir primero autorización de reasignación
- luego `pick` asistido
- finalmente dejar documentados los gates para polling/cola

## Rollback

- si `pick` genera ambigüedad, se revierte manteniendo `list` + `claim` manual
- si la autorización de reasignación causa incompatibilidad temporal, se puede volver al modelo de
  reasignación explícita actual mientras se conserva la auditoría ya existente
