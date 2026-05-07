# Policy: Approval via CLI vs Gateway

Spanish mirror: [docs/es/approval-policy-cli-vs-gateway.es.md](./es/approval-policy-cli-vs-gateway.es.md)

Source: `docs/approval-policy-cli-vs-gateway.md`  
Last updated: 2026-05-07

**Version:** 1.0 (versioned in repository)  
**Scope:** SoftOS workspace / `sdd-workspace-boilerplate`

## Rule

| Context | Canonical mechanism | Audit |
| --- | --- | --- |
| Developer on local machine with repo checkout and credentials | `flow spec approve <slug> --approver <id>` | Identity in `--approver`; no HTTP trail |
| Integrations / automation / teams without checkout | Gateway intents and webhooks under configured auth (`SOFTOS_GATEWAY_*`) | `auth_audit` + task timeline |

## Mandatory

- Do not approve specs in **shared production** with personal CLI only when team policy requires **gateway** approval (define during onboarding).
- Any temporary exception must be recorded with `flow ops decision-log add` (human actor).

## Enforcement (gateway API)

- Variable: `SOFTOS_GATEWAY_ENFORCE_APPROVER_ON_SPEC_APPROVE` (`1` / `true` / `yes` enables).
- Behavior: in `POST /v1/intents` with `intent: spec.approve`, `payload` **must** include non-empty `approver`; otherwise response is `400` with `detail.code = APPROVER_REQUIRED`.
- Default (variable disabled): compatibility mode for clients omitting `approver` (recommended only in dev).

## Short commands (webhooks / comments)

- **GitHub** `issue_comment`: one line `approve <slug>`, `/approve <slug>`, `lgtm <slug>` -> `spec.approve`; `review <slug>` -> `spec.review`.
- **Jira**: `comment.body` with same format (payload should include `issue` + `comment` per automation).
- **Slack**: command text accepts same format before long parser `workflow|spec|...`.

## References

- Integrations runbook: `docs/process-and-integrations-runbook.md`
- Gateway hardening: `specs/features/softos-platform-hardening-security-and-secrets.spec.md`
