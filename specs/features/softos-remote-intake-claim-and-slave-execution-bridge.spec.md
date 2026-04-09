---
schema_version: 3
name: SoftOS Remote Intake Claim And Slave Execution Bridge
description: Permitir que flow en un workspace slave consuma intakes/specs desde un gateway remoto, haga claim exclusivo para un developer, genere plan local y publique heartbeat/transiciones/release al gateway. Debe soportar seleccion explicita por el developer y reasignacion auditada cuando corresponda.
status: approved
owner: platform
single_slice_reason: ""
multi_domain: false
phases: []
depends_on:
  - ../../specs/000-foundation/spec-as-source-operating-model.spec.md
  - ../../specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - ../../specs/000-foundation/repo-routing-and-worktree-orchestration.spec.md
  - ../../specs/features/softos-central-spec-registry-and-claiming.spec.md
  - ../../specs/features/softos-gateway-intake-and-collaboration-loop.spec.md
required_runtimes: []
required_services: []
required_capabilities: []
stack_projects: []
stack_services: []
stack_capabilities: []
targets:
  - ../../flow
  - ../../flowctl/**
  - ../../gateway/app/**
  - ../../gateway/tests/**
  - ../../scripts/bootstrap_workspace.py
  - ../../docs/**
  - ../../README.md
  - ../../workspace.config.json
---

# SoftOS Remote Intake Claim And Slave Execution Bridge

## Objetivo

Permitir que `flow` en un workspace `slave` consuma intakes/specs desde un gateway remoto, haga claim exclusivo para un developer, traiga la spec canonica para generar plan local y publique `heartbeat`, `transition` y `release` al gateway. La seleccion debe ser explicita por el developer y la reasignacion debe ser auditada.

## Contexto

El workspace ya soporta perfiles `master` y `slave`. El perfil `slave` persiste
`gateway.connection = {"mode":"remote","base_url":"..."}` y `.env.gateway`, pero `flow`
no consume todavia esa conexion remota para operar specs/intakes.

El gateway ya expone:

- registry de specs con `claim`, `heartbeat`, `release`, `transition`, `get` y `list`
- timeline de tareas de intake y ejecucion
- locks exclusivos con TTL y auditoria

La brecha actual es operativa:

- el developer en `slave` no puede listar intakes remotos desde `flow`
- no puede seleccionar uno y convertir esa seleccion en claim exclusivo desde `flow`
- no existe fetch del artefacto canonico de la spec para que `flow plan <slug>` trabaje localmente
- no hay heartbeat ni transicion automatica o semi-automatica desde `flow` hacia el gateway remoto
- no existe flujo explicito de reasignacion auditada

## Foundations Aplicables

- `spec-as-source-operating-model`: la spec remota sigue siendo la fuente de verdad y no debe duplicarse con deriva semantica en el `slave`
- `spec-driven-delivery-and-infrastructure`: el bridge debe respetar gates de plan/ci/release y no saltarse el SDLC
- `repo-routing-and-worktree-orchestration`: el plan local derivado desde intake remoto debe seguir el routing y la politica de slices/worktrees del root

## Domains Aplicables

No aplica domain porque la feature pertenece al plano transversal de orquestacion del SDLC y a la integracion `flow <-> gateway`.

## Problema a resolver

SoftOS ya puede crear intakes y registrar ownership central, pero todavia no puede operar el modo
de trabajo esperado para equipos distribuidos:

1. el developer en `slave` lista specs/intakes pendientes desde el gateway remoto
2. selecciona una spec
3. esa seleccion se convierte en claim exclusivo y visible en gateway
4. `flow` trae la spec canonica y genera plan local
5. mientras trabaja, `flow` mantiene heartbeat y publica cambios de estado
6. nadie mas puede tomar esa spec salvo que el lock expire o exista una reasignacion explicita

Sin ese bridge, el registro remoto sirve como ledger, pero no como plano operativo para planning y ejecucion distribuida.

## Alcance

### Incluye

- comandos `flow` para listar specs/intakes remotos disponibles desde la conexion gateway del `slave`
- seleccion explicita por el developer de una spec/intake remoto
- claim exclusivo remoto con persistencia local del `spec_id`, `actor`, `lock_token` y metadatos minimos de sesion
- fetch del artefacto canonico de la spec desde el gateway para materializar o actualizar la spec local antes de planear
- validacion en `flow` para impedir `plan`, `slice start`, `workflow execute-feature` o transiciones protegidas sin claim remoto vigente
- heartbeat manual o automatico durante operaciones largas
- publicacion de `transition` y `release` al gateway desde `flow`
- reasignacion auditada y explicita, con actor solicitante, actor destino y motivo obligatorio
- documentacion operativa y ejemplos reproducibles para `master` y `slave`

### No incluye

- scheduler de auto-pull que tome specs sin decision humana
- asignacion automatica por carga o balanceo entre developers
- reemplazo completo del registry actual por otro modelo de datos
- UI grafica de intake board
- merge o sincronizacion bidireccional arbitraria de specs divergentes entre `master` y `slave`

## Repos afectados

| Repo | Targets |
| --- | --- |
| `sdd-workspace-boilerplate` | `../../flow`, `../../flowctl/**`, `../../gateway/app/**`, `../../gateway/tests/**`, `../../scripts/bootstrap_workspace.py`, `../../docs/**`, `../../README.md`, `../../workspace.config.json` |

## Resultado esperado

- un workspace `slave` puede trabajar contra un gateway remoto usando `flow` como cliente operativo
- la seleccion de una spec remota queda reflejada como claim exclusivo en gateway y bloquea a otros developers
- `flow` puede generar plan local usando la spec canonica descargada del gateway
- el estado de gateway se mantiene alineado con el ciclo operativo real del developer
- toda liberacion o reasignacion queda auditada

## Reglas de negocio

- la seleccion de intake por el developer no es una lectura pasiva; debe convertirse en `claim` exclusivo remoto
- mientras exista lock vigente, otro actor debe recibir error deterministico de conflicto al intentar tomar la misma spec
- `flow` no puede generar plan ni avanzar estados protegidos si el actor local no posee el claim remoto vigente
- la spec usada para planning debe provenir del artefacto canonico expuesto por el gateway; no se permite planear con una copia local huerfana o desactualizada
- `in_edit` e `in_execution` requieren lock activo, conforme al contrato del registry
- el vencimiento del TTL libera la spec y permite un nuevo claim
- la reasignacion no puede ocurrir de manera implicita; requiere accion explicita y auditoria
- la reasignacion debe registrar como minimo `requested_by`, `from_actor`, `to_actor`, `reason` y `source`
- `release` libera el lock; `closed` no implica por si mismo reasignacion retroactiva

## Actores

- developer en `slave`: lista, selecciona, reclama, planifica, envia heartbeat y reporta transiciones
- gateway `master`: fuente de verdad del registry y del artefacto canonico de la spec
- actor autorizado de coordinacion: puede aprobar o ejecutar reasignacion

## Superficies afectadas

- CLI `flow`
- modulos `flowctl` para cliente remoto del gateway y guardrails de ownership
- API del gateway para fetch de artefacto de spec y reasignacion
- bootstrap `slave` para dejar visible la conexion remota de manera consumible por `flow`
- documentacion y ejemplos operativos

## Contrato remoto minimo

### Lectura

- `GET /v1/specs?state=...&assignee=...` para listar disponibilidad
- `GET /v1/specs/{id}` para leer estado y auditoria
- endpoint nuevo para fetch de spec canonica, por ejemplo `GET /v1/specs/{id}/source`

El fetch canonico debe devolver como minimo:

- `spec_id`
- `path` o slug canonico
- contenido markdown completo de la spec
- hash o `updated_at` para detectar staleness

### Mutacion

- `POST /v1/specs/{id}/claim`
- `POST /v1/specs/{id}/heartbeat`
- `POST /v1/specs/{id}/transition`
- `POST /v1/specs/{id}/release`
- endpoint nuevo para reasignacion explicita, por ejemplo `POST /v1/specs/{id}/reassign`

## Contrato CLI esperado

La implementacion puede ajustar el nombre exacto de subcomandos, pero debe cubrir este contrato funcional:

- listar specs/intakes remotos elegibles para trabajo local
- hacer claim explicito de una spec remota
- descargar o refrescar la spec canonica local
- generar plan solo cuando exista claim vigente
- enviar heartbeat
- publicar transicion de estado
- liberar o cerrar claim
- solicitar o ejecutar reasignacion autorizada

La CLI debe usar `workspace.config.json` y/o `.env.gateway` cuando `gateway.connection.mode=remote`.

## Flujo principal

1. El developer en `slave` ejecuta `flow` para listar specs/intakes disponibles en gateway.
2. Selecciona una spec concreta.
3. `flow` ejecuta `claim` remoto y recibe `lock_token`.
4. `flow` descarga la spec canonica remota y la materializa o actualiza localmente.
5. `flow plan <slug>` genera el plan local usando esa spec materializada.
6. Durante el trabajo local, `flow` renueva heartbeat.
7. `flow` publica `transition` a estados relevantes del registry.
8. Al terminar, `flow` libera el lock o marca transicion final y luego libera, segun la politica operativa.

## Flujo de reasignacion

1. Un segundo developer o coordinador detecta que una spec ya esta tomada.
2. Se solicita reasignacion explicita indicando actor destino y motivo.
3. El gateway valida permisos y registra auditoria.
4. El lock previo se libera o se transfiere de forma controlada.
5. El nuevo actor puede continuar con heartbeat y planning o ejecucion.

## Contrato funcional

### Inputs clave

- `SOFTOS_GATEWAY_URL`
- `SOFTOS_GATEWAY_API_TOKEN`
- `gateway.connection.mode=remote`
- `spec_id`
- `actor`
- `lock_token`

### Outputs clave

- listado de specs remotas con estado, assignee y disponibilidad
- spec local materializada desde el artefacto canonico remoto
- plan local generado contra la spec seleccionada
- auditoria remota de claim, heartbeat, transition, release y reassign

### Errores esperados

- conflicto por spec ya asignada (`SPEC_ALREADY_CLAIMED`)
- intento de plan o transicion sin lock (`LOCK_REQUIRED`, `LOCK_MISMATCH`)
- transicion invalida (`INVALID_TRANSITION`)
- spec remota inexistente (`SPEC_NOT_FOUND`)
- fetch remoto fallido o artefacto canonico inconsistente

### Side effects relevantes

- actualizacion del registry central de specs
- persistencia local de metadatos minimos de claim remoto para el workspace `slave`
- materializacion o refresh de la spec local
- timeline y auditoria remota de cada evento operativo

## Routing de implementacion

- El repo se deduce desde `targets`.
- Cada slice debe pertenecer a un solo repo.
- El plan operativo vive en `.flow/plans/**`.
- Las dependencias estructurales viven en el frontmatter y deben resolverse antes de aprobar.

## Slice Breakdown

```yaml
- name: gateway-spec-fetch-and-reassign-api
  targets:
    - ../../gateway/app/**
    - ../../gateway/tests/**
    - ../../docs/**
  hot_area: gateway remote spec registry
  depends_on: []

- name: flow-remote-intake-client-and-claim-guardrails
  targets:
    - ../../flow
    - ../../flowctl/**
    - ../../docs/**
  hot_area: flow remote gateway client
  depends_on:
    - gateway-spec-fetch-and-reassign-api

- name: slave-bootstrap-and-operator-runbook
  targets:
    - ../../scripts/bootstrap_workspace.py
    - ../../README.md
    - ../../docs/**
    - ../../workspace.config.json
  hot_area: slave remote gateway onboarding
  depends_on:
    - flow-remote-intake-client-and-claim-guardrails
```

## Criterios de aceptacion

- `flow` puede listar specs/intakes remotos disponibles desde gateway y seleccionar una para trabajo local
- al hacer claim desde `slave`, la spec queda asignada en gateway y otro developer no puede tomarla mientras el lock siga vigente
- `flow` no puede planear ni ejecutar una spec remota sin claim local vigente del actor actual
- `flow` puede publicar `heartbeat`, `transition` y `release` al gateway durante el ciclo de trabajo
- la reasignacion requiere accion explicita y queda auditada en gateway
- `flow` puede traer el artefacto canonico de la spec remota y usarlo para generar plan local sin copiar texto a mano
- si el lock expira o se libera, otro developer puede tomar la spec sin dejar ownership ambiguo

## Verification Matrix

```yaml
- name: gateway-remote-claim-contract
  level: integration
  command: python3 -m pytest -q gateway/tests -k "spec_registry or intake_collaboration"
  blocking_on:
    - ci
  environments:
    - local
    - staging
  notes: valida claim exclusivo, heartbeat, release, transition, fetch canonico y reasignacion auditada

- name: flow-slave-remote-intake-smoke
  level: integration
  command: python3 ./flow ci repo --all --json
  blocking_on:
    - ci
    - release
  environments:
    - local
    - staging
  notes: valida que flow consuma gateway remoto, materialice spec y aplique guardrails de claim antes de planear
```

## Test plan

- tests unit/integration del gateway para fetch canonico, claim, heartbeat, release, transition y reasignacion
- tests del cliente `flow` para listar, reclamar, refrescar spec y bloquear planning sin claim
- smoke manual o automatizado con workspace `master` + workspace `slave` materializado por bootstrap
- evidencia de comandos reproducibles en `docs/**`

## Rollout

- habilitar primero en modo manual/asistido
- mantener comandos explicitos de claim y reasignacion antes de considerar auto-heartbeat o auto-pull
- probar con una spec real desde `master` hacia un `slave` antes de extender a mas developers

## Rollback

- deshabilitar el cliente remoto de `flow` y volver al flujo manual via API del gateway
- conservar registry y auditoria existentes sin migraciones destructivas
- si el fetch canonico remoto falla, `flow` debe abortar planning sin modificar estado local irreversible

## Prohibiciones

- no permitir que `flow` tome automaticamente una spec remota sin seleccion explicita del developer
- no permitir reasignacion silenciosa o implicita al detectar conflicto
- no permitir planning o ejecucion local sobre una spec remota sin verificar claim vigente
- no usar la copia local de la spec como fuente de verdad si el gateway remoto reporta una version mas nueva
