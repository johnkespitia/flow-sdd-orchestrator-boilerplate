# Politica: aprobacion por CLI vs gateway

English source: [docs/approval-policy-cli-vs-gateway.md](../approval-policy-cli-vs-gateway.md)

Source: `docs/approval-policy-cli-vs-gateway.md`  
Last updated: 2026-05-07

**Version:** 1.0 (documento versionado en repositorio)  
**Alcance:** workspace SoftOS / `sdd-workspace-boilerplate`

## Regla

| Contexto | Mecanismo canonico | Auditoria |
| --- | --- | --- |
| Desarrollador en maquina local con checkout y credenciales | `flow spec approve <slug> --approver <id>` | Identidad en `--approver`; sin traza HTTP |
| Integraciones / automatizacion / equipos sin checkout | Intents y webhooks del gateway con auth configurada (`SOFTOS_GATEWAY_*`) | `auth_audit` + timeline de tareas |

## Obligatorio

- No aprobar specs en **produccion compartida** solo con CLI personal si la politica del equipo exige aprobacion por **gateway** (definir en onboarding).
- Toda excepcion temporal debe registrarse con `flow ops decision-log add` (actor humano).

## Enforcement (API gateway)

- Variable: `SOFTOS_GATEWAY_ENFORCE_APPROVER_ON_SPEC_APPROVE` (activa con `1` / `true` / `yes`).
- Comportamiento: en `POST /v1/intents` con `intent: spec.approve`, el `payload` **debe** incluir `approver` no vacio; si no, responde `400` con `detail.code = APPROVER_REQUIRED`.
- Por defecto (variable desactivada): modo compatible con clientes que omiten `approver` (recomendado solo en dev).

## Comandos cortos (webhooks / comentarios)

- **GitHub** `issue_comment`: una linea `approve <slug>`, `/approve <slug>`, `lgtm <slug>` -> `spec.approve`; `review <slug>` -> `spec.review`.
- **Jira**: `comment.body` con el mismo formato (payload debe incluir `issue` + `comment` segun automatizacion).
- **Slack**: el texto del comando acepta el mismo formato antes del parser largo `workflow|spec|...`.

## Referencias

- Runbook de integraciones: `docs/process-and-integrations-runbook.md`
- Hardening de gateway: `specs/features/softos-platform-hardening-security-and-secrets.spec.md`
