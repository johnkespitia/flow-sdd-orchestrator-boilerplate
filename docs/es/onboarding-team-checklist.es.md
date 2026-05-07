# Checklist de onboarding - operacion SoftOS (T25)

English source: [docs/onboarding-team-checklist.md](../onboarding-team-checklist.md)

Source: `docs/onboarding-team-checklist.md`  
Last updated: 2026-05-07

- [ ] Acceso al repositorio y politica de ramas acordada.
- [ ] `python3 ./flow doctor` sin errores bloqueantes en maquina local.
- [ ] Tokens listos: `SOFTOS_GATEWAY_API_TOKEN` (si API), y secretos GitHub/Jira/Slack segun rol.
- [ ] Webhooks apuntando al gateway correcto (`/webhooks/*`) y firma/HMAC verificada.
- [ ] Ejecutar `python3 ./flow ci integration --profile smoke:ci-clean --auto-up --json` en entorno de prueba.
- [ ] Leer `docs/gateway-central-deployment-runbook.md` si operas gateway central.
- [ ] Conocer ubicacion de metricas: `GET /metrics`, `flow ops metrics`, `flow ops sla`.
- [ ] Conocer comando de decision log: `flow ops decision-log list --limit 20 --json`.
