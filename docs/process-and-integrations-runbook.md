# Process And Integrations Runbook

## Objetivo

Este documento resume el flujo operativo completo del workspace, el estado actual de las integraciones (Jira/GitHub/Slack), y las decisiones que se implementaron para que el sistema sea usable en la práctica.

## Arquitectura Operativa Actual

- `flow` es el control plane del SDLC (spec, review, approve, plan, slices, CI).
- `gateway/` es la capa de ingreso HTTP para sistemas externos.
- Los webhooks no ejecutan shell arbitrario; siempre traducen a intents permitidos.
- El estado de tareas del gateway se persiste en `gateway/data/tasks.db`.
- El feedback externo usa providers de `workspace.providers.json`.

## Endpoints Relevantes

- `POST /webhooks/jira`
- `POST /webhooks/github`
- `POST /webhooks/slack/commands`
- `POST /v1/intents`
- `GET /v1/tasks/{task_id}`
- `GET /v1/repos`

## Flujo Base (Spec-Driven)

1. Intake de iniciativa (`workflow.intake`) desde CLI o gateway.
2. Creación de spec draft en `specs/features/<slug>.spec.md`.
3. Refinamiento de spec hasta eliminar `TODO` y dejarla revisable.
4. `flow spec review <slug>` para findings objetivos.
5. `flow spec approve <slug> --approver <id>` para pasar gate.
6. `flow workflow execute-feature <slug> --start-slices` para ejecución.
7. Verificación con `slice verify`, `ci spec`, `ci repo`, `drift`, `contract verify`.

## Integración Jira (Estado Actual)

### Inbound

- Endpoint: `POST /webhooks/jira`.
- Soporta token bearer (`SOFTOS_JIRA_WEBHOOK_TOKEN`).
- Cuando llega issue Jira:
  - usa `summary` como título base.
  - parsea labels `flow-repo:*`, `flow-runtime:*`, `flow-service:*`, `flow-capability:*`, `flow-depends-on:*`.
  - extrae `description` (ADF o texto) y lo propaga a intake/spec.
  - extrae `acceptance_criteria` o `acceptanceCriteria` cuando exista.

### Efecto en Spec

- `description` ya no queda en placeholder por defecto cuando llega desde Jira.
- Se hidratan automáticamente secciones de contexto.
- `acceptance_criteria` se escribe en `## Criterios de aceptacion`.

### Outbound

- Provider `jira-comment` disponible en `workspace.providers.json`.
- Requiere:
  - `SOFTOS_JIRA_BASE_URL`
  - `SOFTOS_JIRA_USER_EMAIL`
  - `SOFTOS_JIRA_API_TOKEN`

## Integración GitHub (Estado Actual)

### Inbound soportado

- `issue_comment`:
  - comandos `/flow ...`
  - keyword shortcut `/spec`, `#spec`, `flow-spec`
- `issues`:
  - `action=opened` con label `flow-spec`
  - `action=labeled` cuando `label.name == flow-spec`

### Comportamiento clave implementado

- Si llega `flow-spec` sin `flow-repo:*`, usa `root` por defecto.
- En shortcut por comentario (`#spec` / `/spec`):
  - no exige label `flow-spec`.
  - usa título del issue/PR + sufijo `- comment #<n>`.
  - prioriza `comment.body` como descripción contextual.
- Idempotencia:
  - si el intake apunta a un slug con spec existente, devuelve `200` con `reason: intake already exists` y no crea tarea fallida.
- Manejo de errores:
  - errores de intent en webhooks devuelven `400` controlado en vez de `500`.

### Outbound

- Provider `github-comment` disponible por feedback provider.
- Requiere token con permisos de comentar issues/PR.
- Nota: aprobar por CLI local no dispara comentario a GitHub automáticamente; para eso debe ejecutarse vía gateway (`/v1/intents` o webhook).

## Integración Slack (Estado Actual)

- Endpoint: `POST /webhooks/slack/commands`.
- Soporta firma Slack (`SOFTOS_SLACK_SIGNING_SECRET`).
- Acepta comandos `/flow ...`.
- Feedback por `slack-webhook` si está habilitado.

## Cambios Técnicos Clave Realizados

### `flow add-project`

- Fix de creación de archivos en subdirectorios (evita `FileNotFoundError`).
- Merge profundo de `placeholder_files` para no pisar estructuras completas.
- Aplicación real de `compose_override` de capabilities.
- Soporte de placeholder `{port}` en compose rendering.

### Chasis root-only

- Limpieza de `Makefile` para eliminar supuestos fijos `backend/frontend`.
- Targets genéricos por servicio (`SERVICE=<compose_service>`).

### CI

- `root-ci` instala `PyYAML` antes de `flow doctor`.
- En `push`, spec governance usa `--changed` (base/head) para no caer por specs draft históricas no tocadas en el commit.
- Se agregó `tessl.json` a `workspace.config.json` como `target_root` permitido.
- `root-ci` ya no usa `checkout` con `submodules: recursive`; ahora usa `submodules: false` y luego
  `scripts/ci/normalize_gitmodules.sh` para normalizar URLs de `.gitmodules` a relativas cuando aplica y
  ejecutar `git submodule sync/update`.
- El checkout de `root-ci` usa `token: ${{ secrets.GH_PAT || github.token }}` para permitir acceso a
  submódulos privados en otros repos cuando `github.token` no alcanza.
- `Repo CI` corre en job separado con strategy matrix por repo/runtime (`discover-repo-ci-matrix` + `repo-ci`),
  instala toolchains de forma condicional por runtime y ejecuta `flow ci repo <repo>` en modo nativo con
  `FLOW_SKIP_COMPOSE_WRAP=1` para no depender de contenedores en GitHub Actions.

### Secret scan

- Reducción de falsos positivos de `generic-secret` en código fuente (`settings.xxx_secret`, referencias de objetos, etc.).

## Operación Diaria Recomendada

1. Intake desde Jira/GitHub/Slack o `/v1/intents`.
2. Refinamiento y review de spec en PR.
3. Aprobación operativa por gateway cuando se necesite trazabilidad externa.
4. Ejecución de slices y CI.
5. Feedback automático a issue/ticket/canal según provider.

## Limitaciones Actuales

- El gateway corre en entorno local/devcontainer (no multi-equipo por defecto).
- La base de datos del gateway es SQLite local.
- Algunos workflows siguen orientados a operación por desarrollador y no RBAC centralizado.

## Recomendación de Producción

- Gateway centralizado (siempre activo) + URL estable.
- DB compartida (Postgres) para tasks.
- Secret manager central.
- RBAC/autenticación fuerte para `/v1/intents`.
- Workers dedicados para ejecución de intents en paralelo controlado.
