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

Para inspeccionar el claim local/remoto resumido:

```bash
python3 ./flow gateway status <spec-id> --json
python3 ./flow gateway current <spec-id> --json
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

Si quieres selección asistida en vez de elegir manualmente desde `list`, puedes usar:

```bash
python3 ./flow gateway pick --actor <tu-actor> --json
```

`pick` solo considera specs elegibles y termina en un `claim` explícito y auditable. No ejecuta
plan ni slices automáticamente.

Si quieres una ola más autónoma pero todavía acotada, puedes usar:

```bash
python3 ./flow gateway poll --actor <tu-actor> --json
python3 ./flow gateway poll --actor <tu-actor> --auto-plan --json
python3 ./flow gateway watch --actor <tu-actor> --interval-seconds 15 --timeout-seconds 600 --json
python3 ./flow gateway watch --actor <tu-actor> --auto-plan --interval-seconds 15 --timeout-seconds 600 --json
```

Reglas:

- `poll` intenta una sola vez reclamar la primera spec elegible
- `watch` repite `poll` con backoff hasta reclamar una spec o alcanzar sus límites
- sin gate explícito, ninguno de los dos ejecuta `plan`, slices, `release` ni transitions automáticamente
- ambos fallan si el workspace ya tiene un `gateway_claim` local vigente
- `--auto-plan` y `gateway.execution.auto_plan` ya quedan soportados como gate opt-in para la ola
  `claim -> plan`
- si el gate está activo y el claim/fetch sale bien, el comando ejecuta exactamente un `flow plan`
- el comando se detiene después de `plan`, incluso si el plan fue exitoso

### 3. Planear localmente

```bash
python3 ./flow plan <spec-id>
```

En modo `slave`, `flow plan` exige claim remoto vigente. Si el claim expiró, fue liberado o fue
reasignado a otro actor, el comando falla hasta que el developer vuelva a reclamar la spec.

Mientras `plan`, `slice start` o `slice verify` corren con claim vigente, `flow` renueva heartbeat
automáticamente y publica transitions controladas desde los hitos SDLC permitidos por la spec.

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

El hook automático actual usa transiciones explícitas y limitadas:

- `plan` exitoso -> `triaged`
- `slice start` exitoso -> `in_edit`
- `slice verify` exitoso -> `in_review`

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

Para validar el modo autónomo acotado:

```bash
python3 ./flow gateway poll --actor <tu-actor> --json
python3 ./flow gateway watch --actor <tu-actor> --interval-seconds 5 --timeout-seconds 30 --json
```

Para validar específicamente la ola `claim -> plan`:

```bash
python3 ./flow gateway poll --actor <tu-actor> --auto-plan --json
python3 ./flow gateway watch --actor <tu-actor> --auto-plan --interval-seconds 5 --timeout-seconds 30 --max-attempts 6 --json
```

Smoke esperado para `poll --auto-plan` cuando encuentra trabajo:

- `picked=true`
- `plan_attempted=true`
- `plan_status=passed`
- `reason=claimed-and-planned`
- `remote_claim_still_valid=true`
- el comando deja `.flow/plans/<spec-id>.json`
- el flujo se detiene sin arrancar `slice start`, `slice verify` ni `release`

Smoke esperado para `watch --auto-plan` cuando encuentra trabajo antes del timeout:

- el loop se detiene al primer claim exitoso
- ejecuta exactamente un `flow plan <spec-id>`
- devuelve la misma metadata final de `poll --auto-plan`
- no vuelve a iterar después de `plan`, incluso si el plan fue exitoso

Smoke esperado cuando no hay trabajo o no alcanza sus límites:

- `picked=false`
- `plan_attempted=false`
- `plan_status=not-requested`
- `reason=timeout` o `reason=max-attempts-reached`

Smoke esperado cuando el `plan` falla después del claim:

- `picked=true`
- `plan_attempted=true`
- `plan_status=failed`
- `reason=plan-failed-after-claim` o `reason=claim-not-valid-for-plan`
- no hay retry automático hacia otra spec
- no hay `release` automático

Si quieres dejar el gate preparado por workspace:

```json
{
  "gateway": {
    "execution": {
      "auto_plan": false
    }
  }
}
```

## Referencias

- `README.md`
- `docs/gateway-central-deployment-runbook.md`
- `docs/spec-registry-state-contract.md`
- `gateway/README.md`
