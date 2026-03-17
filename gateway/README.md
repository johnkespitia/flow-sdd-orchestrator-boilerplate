# Gateway

Servicio FastAPI que expone adapters inbound para Jira, Slack y GitHub y traduce eventos externos
a intents controlados sobre `python3 ./flow`.

## Endpoints

- `GET /healthz`
- `GET /v1/repos`
- `POST /v1/intents`
- `GET /v1/tasks/{task_id}`
- `POST /webhooks/slack/commands`
- `POST /webhooks/github`
- `POST /webhooks/jira`

## Notas

- Esta primera version usa una cola secuencial persistida en SQLite para evitar colisiones en Git.
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

## Intents soportados

- `status.get`
- `spec.create`
- `spec.review`
- `spec.approve`
- `plan.create`
- `slice.verify`
- `ci.spec`

## Codigos de repo

Para `spec.create`, labels `flow-repo:<...>` y comandos tipo `/flow spec create ... --repo ...`,
el valor puede ser:

- el id real del repo en `workspace.config.json`
- `root` para el repo raiz del workspace
- un alias explicito si el repo declara `code`, `gateway_code`, `aliases` o `gateway_aliases`

Si el cliente no conoce esos codigos, puede descubrirlos con `GET /v1/repos`.

`spec.create` tambien acepta metadata declarativa:

- flags CLI `/flow spec create ... --runtime <pack> --service <pack> --capability <capability> --depends-on <spec>`
- labels inbound `flow-runtime:<pack>`, `flow-service:<pack>`, `flow-capability:<capability>` y `flow-depends-on:<spec>`
