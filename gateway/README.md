# Gateway

Servicio FastAPI que expone adapters inbound para Jira, Slack y GitHub y traduce eventos externos
a intents controlados sobre `python3 ./flow`.

## Endpoints

- `GET /healthz`
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

## Intents soportados

- `status.get`
- `spec.create`
- `spec.review`
- `spec.approve`
- `plan.create`
- `slice.verify`
- `ci.spec`
