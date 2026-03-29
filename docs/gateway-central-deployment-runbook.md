# Runbook: despliegue central del gateway (Ola B / T05)

## Objetivo

Operar un único gateway SoftOS compartido por el equipo sin romper el modo local (workspace en máquina de desarrollo con SQLite y secretos relajados).

## Variables de entorno relevantes

| Variable | Uso |
| --- | --- |
| `FLOW_WORKSPACE_ROOT` | Raíz del workspace (obligatorio en central; default en script de arranque). |
| `SOFTOS_GATEWAY_DB` o `SOFTOS_GATEWAY_DB_URL` | Persistencia de tareas (SQLite path o URL Postgres). |
| `SOFTOS_GATEWAY_API_TOKEN` | Autenticación `Authorization: Bearer` en `/v1/intents`. |
| `SOFTOS_GITHUB_WEBHOOK_SECRET` / `SOFTOS_JIRA_WEBHOOK_TOKEN` / `SOFTOS_SLACK_SIGNING_SECRET` | Validación de webhooks (producción: definir siempre). |
| `SOFTOS_GATEWAY_SECRETS_FILE` | Override explícito para el archivo central de secretos. |
| `SOFTOS_GATEWAY_PORT` / `SOFTOS_GATEWAY_HOST` | Bind del servicio (default `0.0.0.0:8010`). |

## Fuente central de secretos

El gateway lee secretos en este orden:

1. archivo explícito en `SOFTOS_GATEWAY_SECRETS_FILE`
2. `workspace.secrets.json` en la raíz del workspace
3. `gateway/data/secrets.json` como compatibilidad temporal
4. variables de entorno

En despliegue compartido, la fuente preferida debe ser `workspace.secrets.json`.

## Arranque

Desde la raíz del repo:

```bash
chmod +x scripts/gateway_central_start.sh
./scripts/gateway_central_start.sh
```

Equivale a `python3 -m uvicorn app.main:app` con `cwd=gateway/` y `FLOW_WORKSPACE_ROOT` apuntando al workspace desplegado.

## Smoke / health

```bash
SOFTOS_GATEWAY_URL=https://gateway.example.internal ./scripts/gateway_central_smoke.sh
```

Por defecto comprueba `http://127.0.0.1:8010/healthz`. Debe terminar con exit code 0.

## Modo local

No es necesario el script central si ya usas otro proceso (IDE, docker-compose propio). Los mismos endpoints (`GET /healthz`) aplican; el script solo fija convenciones de entorno.

## Referencias

- Política de feedback y reintentos: `docs/feedback-retry-policy.md`
- API del gateway: `gateway/README.md`
