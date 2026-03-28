# Checklist de onboarding — operación SoftOS (T25)

- [ ] Acceso al repositorio y política de ramas acordada.
- [ ] `python3 ./flow doctor` sin errores bloqueantes en máquina local.
- [ ] Tokens: `SOFTOS_GATEWAY_API_TOKEN` (si API), secretos GitHub/Jira/Slack según rol.
- [ ] Webhooks apuntando al gateway correcto (`/webhooks/*`) y firma/HMAC verificada.
- [ ] Ejecutar `python3 ./flow ci integration --profile smoke:ci-clean --auto-up --json` en entorno de prueba.
- [ ] Leer `docs/gateway-central-deployment-runbook.md` si operas gateway central.
- [ ] Saber ubicación de métricas: `GET /metrics`, `flow ops metrics`, `flow ops sla`.
- [ ] Saber decisión registrada: `flow ops decision-log list --limit 20 --json`.
