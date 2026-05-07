# Payloads canónicos de webhooks (gateway)

Spanish mirror: [docs/es/webhook-canonical-payloads.es.md](./es/webhook-canonical-payloads.es.md)

Source: `docs/webhook-canonical-payloads.md`  
Last updated: 2026-05-06

Este documento cumple el criterio de **runbook operativo con payloads canónicos** para integraciones Jira, GitHub y Slack contra `gateway/`. Los ejemplos son mínimos y alineados con `gateway/tests/fixtures/*_v1.*` y con la validación en `gateway/app/webhook_validation.py`.

## Convenciones comunes

- Todos los webhooks se traducen a intents permitidos (no shell arbitrario).
- Errores de esquema devuelven `400` con `detail: { code, message }`.
- Rate limit: `429` con `detail.code = RATE_LIMIT_EXCEEDED` cuando aplica.
- Autenticación: ver variables en `gateway/app/config.py` y `docs/process-and-integrations-runbook.md`.

## GitHub — `issues` abierto con intake de spec

`POST /webhooks/github`  
Headers mínimos: `X-GitHub-Event: issues`

```json
{
  "action": "opened",
  "issue": {
    "number": 1001,
    "title": "Mi feature",
    "body": "Contexto opcional",
    "comments_url": "https://api.github.com/repos/acme/repo/issues/1001/comments",
    "labels": [
      { "name": "flow-spec" },
      { "name": "flow-repo:root" }
    ]
  },
  "repository": {
    "full_name": "acme/repo"
  }
}
```

## GitHub — comentario en issue

`POST /webhooks/github`  
Headers: `X-GitHub-Event: issue_comment` (u evento que incluya `issue` + `comment` según validación)

```json
{
  "action": "created",
  "comment": {
    "id": 2222,
    "body": "/spec mi-slug --title \"Titulo\" --repo root"
  },
  "issue": {
    "number": 1002,
    "title": "Titulo issue",
    "body": "Cuerpo",
    "comments_url": "https://api.github.com/repos/acme/repo/issues/1002/comments",
    "labels": [{ "name": "flow-repo:root" }]
  },
  "repository": {
    "full_name": "acme/repo"
  }
}
```

## Jira — issue con resumen y labels

`POST /webhooks/jira`  
Autenticación: según configuración (token/bearer documentado en runbook de integraciones).

```json
{
  "issue": {
    "key": "PROJ-123",
    "fields": {
      "summary": "Titulo desde Jira",
      "description": "Descripcion o contexto",
      "labels": ["flow-repo:root"]
    }
  }
}
```

## Slack — comando slash

`POST /webhooks/slack/commands`  
Content-Type: `application/x-www-form-urlencoded`  
Firma: `X-Slack-Signature`, timestamp: `X-Slack-Request-Timestamp`

Campos mínimos del form:

| Campo         | Ejemplo |
|---------------|---------|
| `text`        | `workflow intake mi-slug --title "Titulo" --repo root` |
| `response_url`| `https://hooks.slack.com/...` |
| `ssl_check`   | `0` (producción) |

Ejemplo JSON equivalente para pruebas locales (mismo contenido que `slack_command_v1.json`):

```json
{
  "text": "workflow intake sample-spec --title \"Sample Spec\" --repo root",
  "response_url": "https://example.test/slack-response",
  "channel_id": "C123456",
  "ssl_check": "0"
}
```

## Referencias

- Contrato de eventos de timeline: `docs/flow-json-contract.md`
- Integración y endpoints: `docs/process-and-integrations-runbook.md`
- Fixtures versionados: `gateway/tests/fixtures/`
