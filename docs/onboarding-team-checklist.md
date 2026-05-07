# Onboarding Checklist - SoftOS Operations (T25)

Spanish mirror: [docs/es/onboarding-team-checklist.es.md](./es/onboarding-team-checklist.es.md)

Source: `docs/onboarding-team-checklist.md`  
Last updated: 2026-05-07

- [ ] Repository access and branch policy agreed.
- [ ] `python3 ./flow doctor` has no blocking errors on local machine.
- [ ] Tokens ready: `SOFTOS_GATEWAY_API_TOKEN` (if API), plus GitHub/Jira/Slack secrets by role.
- [ ] Webhooks point to correct gateway (`/webhooks/*`) and signature/HMAC is verified.
- [ ] Run `python3 ./flow ci integration --profile smoke:ci-clean --auto-up --json` in a test environment.
- [ ] Read `docs/gateway-central-deployment-runbook.md` if you operate the central gateway.
- [ ] Know metrics locations: `GET /metrics`, `flow ops metrics`, `flow ops sla`.
- [ ] Know decision log command: `flow ops decision-log list --limit 20 --json`.
