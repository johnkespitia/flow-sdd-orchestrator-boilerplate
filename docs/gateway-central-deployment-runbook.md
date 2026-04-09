# Runbook: despliegue portable del gateway (Ola B / T05)

## Objetivo

Operar un único gateway SoftOS compartido por el equipo sin romper el modo local (workspace en máquina de desarrollo con SQLite y secretos relajados).

El contrato de despliegue es proveedor-agnóstico: Render, Railway, Fly.io, VM, systemd,
Docker Compose o Kubernetes deben apuntar al mismo artefacto y al mismo comando de arranque.

Este runbook aplica al perfil de bootstrap `master`. En SoftOS, `master` es el perfil que
instala el control plane completo, incluyendo `gateway/`. El perfil `slave` excluye `gateway/`
y se conecta a un gateway remoto ya existente.

## Artefacto desplegable

El artefacto desplegable no es `gateway/` aislado. Es el workspace completo, porque el gateway
ejecuta `python3 ./flow ...` desde la raíz del repo.

En términos de perfiles SoftOS:

- `master`: este contrato aplica completo y es el perfil portable para desplegar gateway
- `slave`: no despliega gateway; consume uno remoto

Requisitos mínimos del runtime:

- checkout completo del repo
- `python3`
- dependencias Python del gateway instaladas en el entorno
- `FLOW_WORKSPACE_ROOT` apuntando a la raíz del checkout
- `./flow` presente en esa raíz
- base de datos persistente externa para producción, preferiblemente Postgres

## Variables de entorno relevantes

| Variable | Uso |
| --- | --- |
| `FLOW_WORKSPACE_ROOT` | Raíz del workspace (obligatorio en central; default en script de arranque). |
| `SOFTOS_GATEWAY_DB` o `SOFTOS_GATEWAY_DB_URL` | Persistencia de tareas (SQLite path o URL Postgres). |
| `SOFTOS_GATEWAY_API_TOKEN` | Autenticación `Authorization: Bearer` en `/v1/intents`. |
| `SOFTOS_GITHUB_WEBHOOK_SECRET` / `SOFTOS_JIRA_WEBHOOK_TOKEN` / `SOFTOS_SLACK_SIGNING_SECRET` | Validación de webhooks (producción: definir siempre). |
| `SOFTOS_GATEWAY_SECRETS_FILE` | Override explícito para el archivo central de secretos. |
| `SOFTOS_GATEWAY_PORT` / `SOFTOS_GATEWAY_HOST` | Bind del servicio (default `0.0.0.0:8010`). |
| `SOFTOS_GATEWAY_FLOW_BIN` | Binario para invocar `flow` (default `python3`). |
| `SOFTOS_GATEWAY_FLOW_ENTRYPOINT` | Entry point de `flow` relativo al workspace (default `./flow`). |
| `SOFTOS_DEFAULT_FEEDBACK_PROVIDER` | Provider de feedback por defecto. Para fase 1 suele ser `local-log`. |

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

Secuencia correcta con la configuración actual de SoftOS:

1. materializar o bootstrapear un workspace con perfil `master`
2. dentro de ese workspace, ejecutar `python3 ./flow init`
3. para despliegue externo, arrancar el gateway con `bash scripts/gateway_central_start.sh`

Ejemplo end-to-end con el modelo actual:

```bash
python3 scripts/bootstrap_workspace.py /srv/softos-master \
  --project-name "SoftOS Master" \
  --root-repo softos-master \
  --profile master

cd /srv/softos-master
python3 ./flow init
SOFTOS_GATEWAY_PORT="${PORT:-8010}" bash scripts/gateway_central_start.sh
```

Comando portable recomendado para cualquier proveedor:

```bash
SOFTOS_GATEWAY_PORT="${PORT:-8010}" bash scripts/gateway_central_start.sh
```

## Producción

Para entornos externos, usa este baseline:

- `FLOW_WORKSPACE_ROOT=<ruta-al-root-del-checkout>`
- `SOFTOS_GATEWAY_FLOW_BIN=python3`
- `SOFTOS_GATEWAY_FLOW_ENTRYPOINT=./flow`
- `SOFTOS_GATEWAY_DB_URL=postgresql://...`
- `SOFTOS_GATEWAY_API_TOKEN=<token-largo-y-privado>`
- `SOFTOS_DEFAULT_FEEDBACK_PROVIDER=local-log`

Recomendaciones:

- no uses `Root Directory=gateway`; despliega desde la raíz del repo
- no uses SQLite local en plataformas con filesystem efímero
- si el proveedor soporta Docker, usa el `Dockerfile` raíz del workspace
- no intentes modelar el perfil con `flow init --master`; el perfil ya viene dado por el bootstrap del workspace

## Docker portable

Se incluye un `Dockerfile` en la raíz del repo para empacar el workspace completo y arrancar
el gateway con el mismo contrato.

Build:

```bash
docker build -t softos-gateway:local .
```

Run:

```bash
docker run --rm -p 8010:8010 \
  -e FLOW_WORKSPACE_ROOT=/app \
  -e SOFTOS_GATEWAY_DB_URL=postgresql://user:pass@host:5432/postgres \
  -e SOFTOS_GATEWAY_API_TOKEN=change-me \
  -e SOFTOS_DEFAULT_FEEDBACK_PROVIDER=local-log \
  softos-gateway:local
```

Para prueba local con Compose, usa `docker-compose.gateway.yml`.

Ejemplo con workspace `master` ya materializado:

```bash
cd /srv/softos-master
docker build -t softos-gateway:local .
docker run --rm -p 8010:8010 \
  -e FLOW_WORKSPACE_ROOT=/app \
  -e SOFTOS_GATEWAY_DB_URL=postgresql://user:pass@host:5432/postgres \
  -e SOFTOS_GATEWAY_API_TOKEN=change-me \
  -e SOFTOS_DEFAULT_FEEDBACK_PROVIDER=local-log \
  softos-gateway:local
```

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
- Empaquetado portable: `Dockerfile`, `docker-compose.gateway.yml`
