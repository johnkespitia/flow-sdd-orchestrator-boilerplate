# Smoke ci clean contract

English source: [docs/smoke-ci-clean-contract.md](../smoke-ci-clean-contract.md)

Source: `docs/smoke-ci-clean-contract.md`  
Last updated: 2026-05-06

Nota: Este espejo en espanol fue creado para cerrar el backlog de i18n. Se recomienda refinar la traduccion en una iteracion posterior.

# Contrato oficial: perfil `smoke:ci-clean` (Ola C / T07)

Spanish mirror: [docs/es/smoke-ci-clean-contract.es.md](./es/smoke-ci-clean-contract.es.md)

Source: `docs/smoke-ci-clean-contract.md`  
Last updated: 2026-05-06

## Alcance

El perfil `smoke:ci-clean` de `python3 ./flow ci integration` es el **gate de integración estricto** del workspace: valida Compose, opcionalmente levanta el stack (`--auto-up`), ejecuta comprobaciones de **preflight** por runtime y **smoke** por servicio, y **bloquea** el pipeline si cualquier check termina en `FAIL`.

Implementación de referencia: `flowctl/ci.py` → `command_ci_integration`.

## Perfil y equivalencias

| Valor `--profile` | Modo estricto |
| --- | --- |
| `smoke:ci-clean` | Sí |
| `smoke-ci-clean`, `ci-clean` | Sí (alias) |

Otros perfiles (p. ej. `smoke`) usan preflight en modo **advisory** (`WARN`), no bloqueante.

## Checks obligatorios (orden conceptual)

1. **Docker disponible** — sin `docker` en PATH → `SystemExit`.
2. **Compose config** — `docker compose config --quiet` → `PASS` / `FAIL`.
3. **Secrets / devcontainer** (si `--auto-up` y stack abajo) — materialización de `.devcontainer/.env.generated` → `PASS` / `FAIL`.
4. **Stack bootstrap** — `compose up` con reintentos (`FLOW_CI_STACK_UP_*`) → `PASS` / `FAIL`.
5. **Stack status** — `docker compose ps` → `PASS` / `FAIL`.
6. **Bootstrap runtime** (solo si `--bootstrap-runtime`) — `composer install` / `pnpm install` en el servicio → `PASS` / `FAIL` por intento.
7. **Preflight por repo** — `vendor/`, lockfiles, `node_modules/` según `test_runner` → en `smoke:ci-clean`: `FAIL` si falta requisito; en otros perfiles: `WARN`.
8. **Health por servicio** — espera a `healthy` si existe healthcheck en Compose; timeout/poll globales o por servicio (`FLOW_CI_SERVICE_OVERRIDES`).
9. **Smoke por servicio** — comando definido por servicio (workspace, db, repos…) con reintentos/backoff globales o por servicio.

## Criterios PASS / FAIL

- Cada check se registra como `PASS`, `FAIL` o `WARN`.
- El comando **termina con exit code 1** si **algún** check tiene estado `FAIL`.
- `WARN` no solo falla el proceso (pero deja hallazgos en el reporte).

## Bloqueos explícitos (root-ci)

En `.github/workflows/root-ci.yml`, el job **integration-smoke** ejecuta:

`python3 ./flow ci integration --profile smoke:ci-clean --auto-up --json`

Un fallo en este paso **falla el job** y por tanto el workflow (no `continue-on-error`).

## Variables de entorno relevantes

| Variable | Efecto |
| --- | --- |
| `FLOW_CI_STACK_UP_ATTEMPTS`, `FLOW_CI_STACK_UP_BACKOFF_SECONDS` | Reintentos al levantar stack. |
| `FLOW_CI_SMOKE_ATTEMPTS`, `FLOW_CI_SMOKE_BACKOFF_SECONDS` | Defaults globales para reintentos del smoke por servicio. |
| `FLOW_CI_HEALTH_TIMEOUT_SECONDS`, `FLOW_CI_HEALTH_POLL_SECONDS` | Defaults globales para espera de health. |
| `FLOW_CI_SERVICE_OVERRIDES` | JSON: `{ "nombre_servicio": { "smoke_attempts": 3, "smoke_backoff_seconds": 1, "health_timeout_seconds": 60, "health_poll_seconds": 2 } }`. |
| `FLOW_WORKSPACE_CONTAINER_PATH` | Ruta del workspace dentro del contenedor (default `/workspace`) para `--bootstrap-runtime`. |

## Flags CLI

| Flag | Descripción |
| --- | --- |
| `--bootstrap-runtime` | Opt-in T09: instala dependencias (composer/pnpm) antes del preflight. |
| `--preflight-relaxed` | Bypass T10: desactiva preflight estricto **incluso** en `smoke:ci-clean` (solo diagnóstico; usar con cuidado). |

## Salida JSON

Con `--json`, el payload incluye `contract` con `ci_clean_profile`, `strict_preflight`, `preflight_relaxed`, `bootstrap_runtime` y `service_overrides_keys` para trazabilidad.

## Referencias

- `flowctl/ci.py` — lógica integrada.
- `docs/feedback-retry-policy.md` — reintentos de feedback gateway (alcance distinto).
