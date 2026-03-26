# Spec Registry State Contract

## Estados obligatorios

Cadena valida y estricta:

`new -> triaged -> in_edit -> in_review -> approved -> in_execution -> in_validation -> done -> closed`

Reglas:

- Solo se permite avanzar un paso por transicion.
- Cualquier transicion fuera de la cadena devuelve `INVALID_TRANSITION`.
- `in_edit` e `in_execution` requieren lock activo del actor (`lock_token` + `assignee`).
- Solo existe un assignee activo mientras haya lock vigente.

## Locking

- `POST /v1/specs/{id}/claim` crea o toma lock exclusivo.
- `POST /v1/specs/{id}/heartbeat` renueva TTL del lock.
- `POST /v1/specs/{id}/release` libera lock explicitamente.
- Si expira TTL sin heartbeat, el lock se libera automaticamente con evento de auditoria `lock_expired`.
- Claims concurrentes sobre la misma spec: un solo ganador; el resto recibe `SPEC_ALREADY_CLAIMED`.

## Errores deterministas y auditables

Codigos estables:

- `INVALID_SPEC_ID`
- `SPEC_NOT_FOUND`
- `SPEC_ALREADY_CLAIMED`
- `LOCK_REQUIRED`
- `LOCK_MISMATCH`
- `INVALID_TTL`
- `INVALID_TRANSITION`

Formato de error HTTP:

```json
{
  "detail": {
    "code": "INVALID_TRANSITION",
    "message": "Invalid transition: `triaged` -> `approved`."
  }
}
```

## Auditoria

Cada cambio guarda:

- `event`
- `from_state`
- `to_state`
- `actor`
- `reason`
- `source`
- `timestamp`

Eventos registrados por el contrato:

- `created`
- `claim`
- `heartbeat`
- `release`
- `transition`
- `lock_expired`
