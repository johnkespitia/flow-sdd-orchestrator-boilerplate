# Flow json contract

English source: [docs/flow-json-contract.md](../flow-json-contract.md)

Source: `docs/flow-json-contract.md`  
Last updated: 2026-05-06

Nota: Este espejo en espanol fue creado para cerrar el backlog de i18n. Se recomienda refinar la traduccion en una iteracion posterior.

# Flow JSON Contract

Spanish mirror: [docs/es/flow-json-contract.es.md](./es/flow-json-contract.es.md)

Source: `docs/flow-json-contract.md`  
Last updated: 2026-05-06

`flow` sigue entregando salida legible por humanos por defecto, pero los comandos operativos del
control plane aceptan `--json` para agentes, CI y tooling.

## Comandos cubiertos

- `doctor`
- `status`
- `skills doctor|list|sync`
- `providers doctor|list`
- `submodule doctor|sync`
- `secrets doctor|list|sync|exec|scan`
- `drift check`
- `contract verify`
- `ci spec|repo|integration`
- `release cut|manifest|status|promote`
- `infra plan|apply|status`
- `spec generate-contracts`

## Gateway Event Contract

Para payloads HTTP de entrada (Jira/GitHub/Slack), ver `docs/webhook-canonical-payloads.md`.

Eventos de ciclo de vida emitidos por el gateway (timeline + feedback):

- `created`
- `claimed`
- `comment_added`
- `review_requested`
- `approved`
- `execution_started`
- `execution_failed`
- `execution_succeeded`
- `closed`

Reglas operativas:

- webhooks de Slack/Jira/GitHub solo aceptan mapeo a `workflow.intake`
- si no existe correlacion valida, se registra `failed-intake` con causa auditable
- `closed` se emite cuando `flow` confirma estado final (`closed|done|released`)
- `comment_added` se emite cuando un comentario de tarea se persiste y se notifica al provider externo

Payload JSON canonico de evento:

```json
{
  "event": "execution_succeeded",
  "status": "succeeded",
  "source": "worker",
  "payload": {
    "task_id": "abcd1234",
    "intent": "workflow.execute_feature"
  },
  "created_at": "2026-03-26T16:00:00+00:00"
}
```

## Convención

- siempre imprimir un único objeto JSON en `stdout`
- errores operativos devuelven exit code distinto de `0`
- reportes persistidos siguen viviendo en `.flow/reports/**` o `releases/**`
- el payload debe incluir rutas relativas del repo cuando referencia artefactos

## Ejemplos

```bash
python3 ./flow doctor --json
python3 ./flow ci spec --all --json
python3 ./flow submodule doctor --json
python3 ./flow secrets scan --all --json
python3 ./flow contract verify --all --json
python3 ./flow release status --version 2026.03.14-1 --json
```
