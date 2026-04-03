# SoftOS Full Workflow

Este documento resume el workflow completo que el SoftOS soporta hoy, sin hablar de una visión
futura. Todo lo que aparece aquí ya existe en `flow`, en el stack del devcontainer o en el gateway.

## Qué es el SoftOS

El SoftOS tiene tres capas:

- `flow` como kernel y control plane
- `specs/**` + `.flow/**` como source of truth y estado operativo
- `gateway/` como ingress HTTP para Jira, Slack y GitHub

Regla base:

- los usuarios, agentes e integraciones nunca deberían “inventar” el proceso
- todos deben terminar ejecutando `python3 ./flow ...`

## Superficies actuales

Hoy el sistema ya soporta:

- diseño de stack desde prompt con `flow stack design|plan|apply`
- alta manual de proyectos con `flow add-project`
- gestión de skills con `flow skills`
- gestión de secrets con `flow secrets`
- gestión de providers con `flow providers`
- ciclo SDD completo con `flow spec`, `flow plan`, `flow slice`
- drift y contracts con `flow drift` y `flow contract`
- CI, release e infra con `flow ci`, `flow release`, `flow infra`
- checks de repos/submódulos con `flow submodule`
- entrada externa por Jira, Slack y GitHub mediante `gateway/`

## Workflow 1: Chasis limpio a stack inicial

Este es el flujo para nacer desde cero:

```bash
python3 ./flow doctor
python3 ./flow stack design --prompt "quiero una api en golang con postgresql y graphql" --json
python3 ./flow stack plan --json
python3 ./flow stack apply --json
python3 ./flow status --json
```

Qué pasa:

- `stack design` traduce la intención a `workspace.stack.json`
- `stack plan` muestra qué proyectos, servicios y foundations se crearán
- `stack apply` materializa repos/proyectos, servicios y specs base

Alternativa spec-first:

```bash
python3 ./flow spec review stack-from-spec
python3 ./flow stack plan --spec stack-from-spec --json
python3 ./flow spec approve stack-from-spec --approver alice
python3 ./flow stack design --spec stack-from-spec --json
python3 ./flow stack apply --spec stack-from-spec --json
```

En ese modo la spec aprobada debe declarar `stack_projects`, `stack_services` y `stack_capabilities`.
Para topologias mas explicitas puedes declarar tambien:

- proyecto: `repo_code`, `compose_service`, `aliases`, `env`, `service_bindings`
- proyecto: `default_targets`, `target_roots`, `use_existing_dir`
- servicio: `env`, `ports`, `volumes`

Importante:

- esta V1 usa inferencia heurística local
- no invoca un modelo externo
- la topología resultante sigue pasando por validación del control plane
- el prompt ya solo propone la spec draft; `stack apply` solo consume specs aprobadas
- `stack plan --spec` puede correr sobre drafts review-clean para previsualizar el cambio

## Workflow 2: Agregar proyectos manualmente

Si no quieres partir de un prompt, puedes crecer el workspace explícitamente:

```bash
python3 ./flow add-project api --runtime php --port 8000
python3 ./flow add-project web --runtime pnpm --port 5173
python3 ./flow add-project mobile --runtime pnpm --port 4173
```

Qué hace:

- registra el repo en `workspace.config.json`
- crea el placeholder del proyecto
- resuelve el runtime desde `workspace.runtimes.json`
- agrega servicios al `docker-compose` cuando corresponde

## Workflow 3: Skills, secrets y providers

Para un primer arranque limpio del workspace:

```bash
python3 ./flow init
```

Eso materializa `.devcontainer/.env.generated` si falta, levanta el stack y deja el gateway listo
para smoke checks desde el host.

### Skills

```bash
python3 ./flow skills doctor
python3 ./flow skills list
python3 ./flow skills sync --dry-run
```

### Secrets

```bash
python3 ./flow secrets doctor
python3 ./flow secrets sync
python3 ./flow secrets scan --all --json
```

### Providers

```bash
python3 ./flow providers doctor
python3 ./flow providers list --json
```

Esto cubre:

- capacidades instalables del agente
- generación de `.env` operativos
- adapters de release, infra y feedback

## Workflow 4: Spec-Driven Development

El ciclo normal de una feature es:

```bash
python3 ./flow workflow intake identity-bootstrap --title "Identity Bootstrap" --repo root --runtime go-api --service postgres-service --capability graphql --depends-on spec-as-source-operating-model --json
python3 ./flow workflow next-step identity-bootstrap --json
python3 ./flow spec review identity-bootstrap
python3 ./flow spec approve identity-bootstrap --approver alice
python3 ./flow workflow execute-feature identity-bootstrap --start-slices --json
python3 ./flow slice verify identity-bootstrap api-main
python3 ./flow status --json
```

Qué valida el sistema:

- que la spec exista y tenga frontmatter válido
- que `depends_on`, runtimes, servicios y capabilities existan en el catálogo instalado
- que la spec esté realmente lista antes de aprobar
- que `workflow doctor` mantenga verde BMAD + Tessl como capa orquestadora por defecto
- que haya `[@test]`
- que `## Verification Matrix` sea válida cuando la spec declare pruebas transversales
- que el plan solo ocurra después de `approved`
- que `slice verify` respete estado, ownership y test links

## Workflow 5: Drift y contracts

### Drift

```bash
python3 ./flow drift check --all --json
```

Hoy esto verifica:

- que `targets` resuelvan
- que `[@test]` apunten a tests ejecutables por el runner del repo
- que `Verification Matrix` tenga perfiles ejecutables y etapas bloqueantes válidas
- superficies estructurales que el stack ya puede comprobar

### Contracts

```bash
python3 ./flow spec generate-contracts identity-bootstrap --json
python3 ./flow contract verify --all --json
```

Esto sirve para:

- generar contratos derivados desde la spec
- detectar drift contrato-implementación antes de integración

## Workflow 6: CI, release e infra

### CI

```bash
python3 ./flow ci spec --all --json
python3 ./flow ci repo --all --json
python3 ./flow ci integration --profile smoke --json
```

### Release

```bash
python3 ./flow release cut --version 2026.03.14-1 --spec identity-bootstrap --json
python3 ./flow release status --version 2026.03.14-1 --json
python3 ./flow release promote --version 2026.03.14-1 --env preview --provider local-hooks --json
```

### Infra

```bash
python3 ./flow infra plan identity-bootstrap --env preview --provider local-hooks --json
python3 ./flow infra apply identity-bootstrap --env preview --provider local-hooks --json
python3 ./flow infra status identity-bootstrap --json
```

Si exportas `SOFTOS_SLACK_WEBHOOK_URL`, los hooks locales notifican a Slack cuando una entrega
queda lista (`change ready` al terminar `infra apply`) o cuando falla `release promote`,
`infra plan` o `infra apply`.

## Workflow 7: Stack runtime y operaciones

```bash
python3 ./flow stack doctor
python3 ./flow stack ps
python3 ./flow stack up
python3 ./flow stack down
python3 ./flow stack exec workspace -- pwd
```

Esto es la capa operativa del devcontainer y de los servicios del workspace.

Si trabajas desde el shell host, `flow tessl`, `flow bmad`, `flow skills doctor`, `flow skills sync`
y `flow ci repo` delegan automaticamente al servicio `workspace` cuando el stack ya esta activo.
Para comandos arbitrarios del workspace, usa `python3 ./flow workspace exec -- ...` o
`scripts/workspace_exec.sh ...`.
Para comandos del runtime de un repo, usa `python3 ./flow repo exec <repo> -- ...` para ejecutarlos en el contenedor del proyecto.

## Workflow 8: Repos y guardrails

```bash
python3 ./flow submodule doctor --json
python3 ./flow submodule sync --json
make hooks-install
```

En workspaces con submódulos, esto evita:

- punteros desalineados
- repos dirty sin sincronización
- errores de operación multi-repo

## Workflow 9: Gateway e integraciones inbound

El gateway ya soporta:

- `POST /v1/intents`
- `POST /webhooks/slack/commands`
- `POST /webhooks/github`
- `POST /webhooks/jira`
- `GET /v1/tasks/{task_id}`

Arranque:

```bash
python3 ./flow init
curl -fsSL "http://127.0.0.1:${SOFTOS_GATEWAY_HOST_PORT:-8010}/healthz"
```

Ejemplos:

```bash
curl http://127.0.0.1:${SOFTOS_GATEWAY_HOST_PORT:-8010}/v1/repos
```

```bash
curl -X POST http://127.0.0.1:${SOFTOS_GATEWAY_HOST_PORT:-8010}/v1/intents \
  -H 'Content-Type: application/json' \
  -d '{"source":"api","intent":"status.get","payload":{}}'
```

```bash
curl -X POST http://127.0.0.1:${SOFTOS_GATEWAY_HOST_PORT:-8010}/webhooks/jira \
  -H 'Content-Type: application/json' \
  -d '{"intent":"spec.create","payload":{"slug":"jira-demo","title":"Jira Demo","repos":["root"]}}'
```

```bash
curl -X POST http://127.0.0.1:${SOFTOS_GATEWAY_HOST_PORT:-8010}/webhooks/github \
  -H 'Content-Type: application/json' \
  -H 'X-GitHub-Event: issue_comment' \
  -d '{"comment":{"body":"/flow status"},"issue":{"number":1,"comments_url":"https://api.github.test/repos/acme/demo/issues/1/comments"},"repository":{"full_name":"acme/demo"}}'
```

Comportamiento actual:

- el gateway usa una cola secuencial persistida en SQLite
- no ejecuta shell arbitrario
- traduce eventos externos a intents cerrados
- `GET /v1/repos` expone los codigos validos para clientes externos
- cuando un intent requiere repo, el gateway resuelve codigos desde `workspace.config.json`; `root`
  es el alias estable del repo raiz del workspace
- si el provider real de feedback no está habilitado, usa `local-log`

## Workflow 10: Uso con IA

Hoy el SoftOS no depende de IA para funcionar. La integración correcta con IA es:

1. Claude Code, Codex, Cursor, Gemini o cualquier IDE interpreta la intención
2. la IA llama `python3 ./flow ...` o el `gateway`
3. `flow` valida, materializa y gobierna el SDLC

La IA es cliente del sistema, no el sistema.

## Qué no hace todavía esta versión

Todavía no está resuelto aquí:

- un provider AI formal para `flow stack design`
- marketplace de capabilities
- ejecución multiagente autónoma completa
- despliegues reales a cloud con providers productivos habilitados

Eso queda para la siguiente iteración.

## Prompt inicial recomendado

Para cerrar esta versión y montar un primer sistema desde cero, el prompt inicial recomendado es:

```text
Inicializa un workspace nuevo con una API en Go, PostgreSQL y GraphQL. Quiero que el sistema cree el stack base, las foundations mínimas, deje el gateway activo para Jira/Slack/GitHub y prepare el flujo SDD completo desde spec hasta CI.
```

Si el cliente AI trabaja directo sobre el repo, la secuencia esperada es:

```bash
python3 ./flow stack design --prompt "quiero una api en golang que se conecte a postgresql y sea consumible usando graphql"
python3 ./flow stack plan
python3 ./flow stack apply
python3 ./flow secrets sync
python3 ./flow stack up
python3 ./flow doctor
```
