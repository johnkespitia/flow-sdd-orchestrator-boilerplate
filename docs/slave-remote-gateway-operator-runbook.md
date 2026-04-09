# Runbook: operador `slave` contra gateway remoto

## Objetivo

Operar un workspace `slave` conectado a un gateway `master` remoto para tomar una spec/intake,
bloquearla para otros developers, generar plan local y publicar el estado de trabajo de vuelta
al registry central.

Este runbook asume que el gateway remoto ya existe y que el bootstrap del workspace se hizo con
perfil `slave`.

## Bootstrap

Materializa el runner con perfil `slave`:

```bash
python3 scripts/bootstrap_workspace.py /ruta/slave \
  --project-name "SoftOS Dev Runner" \
  --root-repo softos-dev-runner \
  --profile slave \
  --gateway-url https://gateway.example.internal
```

El bootstrap deja:

- `workspace.config.json` con `gateway.connection.mode=remote`
- `workspace.config.json` con `gateway.connection.base_url=<gateway-url>`
- `.env.gateway` con `SOFTOS_GATEWAY_URL` y `SOFTOS_GATEWAY_API_TOKEN`

Luego inicializa el workspace:

```bash
cd /ruta/slave
python3 ./flow init
```

## Flujo operativo

### 1. Listar specs/intakes disponibles

```bash
python3 ./flow gateway list --json
```

Puedes filtrar por estado o assignee:

```bash
python3 ./flow gateway list --state triaged --json
python3 ./flow gateway list --assignee dev-a --json
```

### 2. Reclamar una spec de forma exclusiva

El developer selecciona una spec y la reclama explícitamente. Mientras el lock siga vigente,
otro developer no puede tomarla.

```bash
python3 ./flow gateway claim <spec-id> --actor <tu-actor> --json
```

Efectos del claim:

- el gateway registra `assignee=<tu-actor>`
- se crea o renueva `lock_token`
- `flow` descarga la spec canónica con `fetch-spec`
- el workspace guarda metadata local en `.flow/state/<spec-id>.json`

Si otro actor intenta reclamarla con lock vigente, el gateway responde `SPEC_ALREADY_CLAIMED`.

### 3. Planear localmente

```bash
python3 ./flow plan <spec-id>
```

En modo `slave`, `flow plan` exige claim remoto vigente. Si el claim expiró, fue liberado o fue
reasignado a otro actor, el comando falla hasta que el developer vuelva a reclamar la spec.

### 4. Mantener el lock mientras trabajas

Renueva el heartbeat durante el trabajo local:

```bash
python3 ./flow gateway heartbeat <spec-id> --json
```

Puedes ajustar el TTL:

```bash
python3 ./flow gateway heartbeat <spec-id> --ttl-seconds 300 --json
```

Si el lock expira, la spec vuelve a quedar disponible para otro developer.

### 5. Publicar transiciones de estado

```bash
python3 ./flow gateway transition <spec-id> triaged --json
```

La transición válida depende del contrato remoto del gateway. `flow` no salta la máquina de
estados del registry. Si intentas una transición inválida, el gateway la rechaza.

### 6. Reasignar explícitamente

La reasignación no es implícita. Requiere una acción explícita y queda auditada:

```bash
python3 ./flow gateway reassign <spec-id> <nuevo-actor> --json
```

Efectos:

- el gateway rota `lock_token`
- cambia `assignee`
- audita el evento `reassign`
- el state local se actualiza con el nuevo actor y el nuevo lock

### 7. Liberar la spec al terminar o al cederla

```bash
python3 ./flow gateway release <spec-id> --json
```

Efectos:

- el gateway limpia `assignee`, `lock_token` y `lock_expires_at`
- `flow` borra `gateway_claim` del state local
- otro developer puede reclamar la spec sin ownership ambiguo

## Artefactos locales

Los comandos de bridge guardan estado en:

- `.env.gateway`
- `workspace.config.json`
- `.flow/state/<spec-id>.json`

Campos esperados en el state local mientras el claim existe:

- `gateway_claim.base_url`
- `gateway_claim.spec_id`
- `gateway_claim.actor`
- `gateway_claim.lock_token`
- `gateway_remote_spec.path`
- `gateway_remote_spec.updated_at`
- `gateway_remote_spec.content_sha256`

## Fallos esperados

- `gateway claim` falla si la spec ya está reclamada por otro actor.
- `flow plan` falla si no existe `gateway_claim` vigente para el actor local.
- `gateway transition` falla si la transición no es válida en el registry remoto.
- `gateway heartbeat` o `release` fallan si el `lock_token` local ya no coincide con el remoto.

## Validación mínima

La secuencia mínima de validación para un `slave` es:

```bash
python3 ./flow gateway list --json
python3 ./flow gateway claim <spec-id> --actor <tu-actor> --json
python3 ./flow plan <spec-id>
python3 ./flow gateway heartbeat <spec-id> --json
python3 ./flow gateway transition <spec-id> triaged --json
python3 ./flow gateway release <spec-id> --json
```

## Referencias

- `README.md`
- `docs/gateway-central-deployment-runbook.md`
- `docs/spec-registry-state-contract.md`
- `gateway/README.md`
