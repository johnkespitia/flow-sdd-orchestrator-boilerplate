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
- `POST /v1/specs/{id}/reassign` transfiere ownership de manera explicita y rota `lock_token`.
- Si expira TTL sin heartbeat, el lock se libera automaticamente con evento de auditoria `lock_expired`.
- Claims concurrentes sobre la misma spec: un solo ganador; el resto recibe `SPEC_ALREADY_CLAIMED`.

## Fetch canonico de spec

- `GET /v1/specs/{id}/source` devuelve el markdown canonico de la spec, su path y un hash estable de contenido.
- El cliente remoto de `flow` debe usar este endpoint para materializar la spec local antes de planear.
- Si la spec no existe en el workspace canonico, el gateway devuelve `SPEC_SOURCE_NOT_FOUND`.

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
- `reassign`
- `lock_expired`

## Spec 1 Closure

Spec 1 (`softos-central-spec-registry-and-claiming`) se considera funcionalmente completo en este workspace para el alcance definido:

- registro central de specs con estados y auditoria
- endpoints de claim/heartbeat/release/transition/get/list
- lock exclusivo con TTL + heartbeat + expiracion automatica
- rechazo de double-claim concurrente (single winner)
- pruebas de concurrencia para claim/release/heartbeat

Evidencia de validacion ejecutada:

- `python3 -m unittest gateway.tests.test_spec_registry_concurrency` -> OK (3 tests, passed)
- `python3 ./flow ci repo --all --json` -> OK (exit 0)
- `python3 ./flow ci spec --all` -> FAIL (exit 1) por deuda legacy de specs preexistentes en el workspace, no por regresion de Spec 1

Comandos reproducibles:

```bash
python3 -m unittest gateway.tests.test_spec_registry_concurrency
python3 ./flow ci repo --all --json
python3 ./flow ci spec --all
```
