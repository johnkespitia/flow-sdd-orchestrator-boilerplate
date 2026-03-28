# Política: aprobación por CLI vs gateway

**Versión:** 1.0 (documento versionado en repo)  
**Alcance:** workspace SoftOS / `sdd-workspace-boilerplate`

## Regla

| Contexto | Mecanismo canónico | Auditoría |
|----------|--------------------|-----------|
| Desarrollador en máquina local con repo y credenciales | `flow spec approve <slug> --approver <id>` | Identidad en `--approver`; sin trail HTTP |
| Integración / automatización / equipos sin checkout | Gateway: intents y webhooks bajo auth configurada (`SOFTOS_GATEWAY_*`) | `auth_audit` + timeline de tareas |

## Obligatorio

- No se aprueba spec en **producción compartida** solo con CLI personal si la política del equipo exige **gateway** (definir en onboarding).
- Cualquier excepción temporal debe registrarse en `flow ops decision-log add` (actor humano).

## Enforcement (gateway API)

- Variable: `SOFTOS_GATEWAY_ENFORCE_APPROVER_ON_SPEC_APPROVE` (`1` / `true` / `yes` activa).
- Comportamiento: en `POST /v1/intents` con `intent: spec.approve`, el `payload` **debe** incluir `approver` no vacío; si no, respuesta `400` con `detail.code = APPROVER_REQUIRED`.
- Por defecto (variable no activa): compatible con clientes existentes que omitan `approver` (solo recomendado en dev).

## Comandos cortos (webhooks / comentarios)

- **GitHub** `issue_comment`: una línea `approve <slug>`, `/approve <slug>`, `lgtm <slug>` → `spec.approve`; `review <slug>` → `spec.review`.
- **Jira**: cuerpo de `comment.body` con el mismo formato (payload debe incluir `issue` + `comment` según automatización).
- **Slack**: el texto del comando acepta el mismo formato antes del parser largo `workflow|spec|...`.

## Referencias

- Runbook de integraciones: `docs/process-and-integrations-runbook.md`
- Hardening gateway: `specs/features/softos-platform-hardening-security-and-secrets.spec.md`
