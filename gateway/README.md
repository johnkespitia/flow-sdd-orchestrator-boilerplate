# Gateway

Servicio FastAPI que expone adapters inbound para Jira, Slack y GitHub y traduce eventos externos
a intents controlados sobre `python3 ./flow`.

## Endpoints

- `GET /healthz`
- `GET /v1/repos`
- `POST /v1/intents`
- `GET /v1/tasks/{task_id}`
- `POST /v1/tasks/{task_id}/comments`
- `POST /v1/specs/{id}/claim`
- `POST /v1/specs/{id}/heartbeat`
- `POST /v1/specs/{id}/release`
- `POST /v1/specs/{id}/transition`
- `GET /v1/specs/{id}`
- `GET /v1/specs?state=...&assignee=...`
- `POST /webhooks/slack/commands`
- `POST /webhooks/github`
- `POST /webhooks/jira`

## Notas

- Esta primera version usa una cola secuencial persistida en SQLite para evitar colisiones en Git.
- En despliegue externo, el artefacto correcto es el workspace completo, no `gateway/` aislado.
- El gateway arranca como servicio separado, pero ejecuta `python3 ./flow` como backend operativo.
- No expone ejecucion arbitraria de shell. Solo intents permitidos.
- Si no hay secretos configurados, las validaciones HMAC/Bearer se relajan para desarrollo local.
- Si el provider especifico de Slack, GitHub o Jira no esta habilitado, el feedback cae en
  `local-log` para no perder el resultado del task durante pruebas locales.
- Para intents que requieren repo, el gateway resuelve codigos usando `workspace.config.json`.
  El alias estable del repo raiz es `root`, aunque el `root_repo` real haya sido renombrado
  por `bootstrap_workspace.py`.
- `spec.review` puede terminar en `completed_with_findings` si la revision se ejecuto bien pero la
  spec aun no queda lista para aprobar.
- `spec.approve` puede incluir `approver` en el payload; si no llega, `flow` registra la identidad
  disponible en `FLOW_APPROVER/USER`.
- Los webhooks Slack/Jira/GitHub se normalizan a `workflow.intake`; cualquier otro intent inbound
  se rechaza con error determinístico y registro `failed-intake`.

## Intents soportados

- `status.get`
- `workflow.intake`
- `workflow.next_step`
- `workflow.execute_feature`
- `spec.create`
- `spec.review`
- `spec.approve`
- `plan.create`
- `slice.verify`
- `ci.spec`

## Codigos de repo

Para `workflow.intake` y `spec.create`, labels `flow-repo:<...>` y comandos tipo `/flow workflow intake ... --repo ...`,
el valor puede ser:

- el id real del repo en `workspace.config.json`
- `root` para el repo raiz del workspace
- un alias explicito si el repo declara `code`, `gateway_code`, `aliases` o `gateway_aliases`

Si el cliente no conoce esos codigos, puede descubrirlos con `GET /v1/repos`.

`workflow.intake` y `spec.create` tambien aceptan metadata declarativa:

- flags CLI `/flow workflow intake ... --runtime <pack> --service <pack> --capability <capability> --depends-on <spec>`
- labels inbound `flow-runtime:<pack>`, `flow-service:<pack>`, `flow-capability:<capability>` y `flow-depends-on:<spec>`

Los webhooks inbound que abren una iniciativa nueva usan `workflow.intake` por defecto. `spec.create`
queda disponible como API de bajo nivel, pero ya no es el happy path recomendado.

## Deploy portable

Contrato mínimo para cualquier proveedor:

- checkout completo del repo
- workspace bootstrapeado como perfil `master`
- `python3`
- `FLOW_WORKSPACE_ROOT` apuntando a la raíz del checkout
- `SOFTOS_GATEWAY_FLOW_BIN=python3`
- `SOFTOS_GATEWAY_FLOW_ENTRYPOINT=./flow`
- `SOFTOS_GATEWAY_DB_URL=postgresql://...` para producción

Comando de arranque recomendado:

```bash
SOFTOS_GATEWAY_PORT="${PORT:-8010}" bash scripts/gateway_central_start.sh
```

Dentro de un workspace `master`, el bootstrap operativo sigue siendo:

```bash
python3 ./flow init
```

El perfil `slave` no incluye `gateway/`; por tanto este contrato no le aplica como artefacto de deploy.

Artefactos incluidos:

- `Dockerfile`
- `docker-compose.gateway.yml`
- `docs/gateway-central-deployment-runbook.md`
