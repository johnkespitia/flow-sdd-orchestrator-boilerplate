# Playbook workflow rollback

English source: [docs/playbook-workflow-rollback.md](../playbook-workflow-rollback.md)

Source: `docs/playbook-workflow-rollback.md`  
Last updated: 2026-05-06

Nota: Este espejo en espanol fue creado para cerrar el backlog de i18n. Se recomienda refinar la traduccion en una iteracion posterior.

# Playbook: rollback de workflows e integraciones (T24)

Spanish mirror: [docs/es/playbook-workflow-rollback.es.md](./es/playbook-workflow-rollback.es.md)

Source: `docs/playbook-workflow-rollback.md`  
Last updated: 2026-05-06

## Objetivo

Restaurar un estado estable cuando un cambio en workflows (`flow workflow run`, integraciones CI o gateway) introduce regresiones.

## Procedimiento (dry-run lógico)

1. **Congelar entradas**: desactivar webhooks o tokens de origen (`SOFTOS_GATEWAY_API_TOKEN` rotado / revocado en proveedor).
2. **Identificar versión buena**: último commit o tag conocido estable del workspace.
3. **Revertir código**: `git revert` o `git checkout <tag> -- flow flowctl gateway` según alcance.
4. **Estado `.flow`**: conservar `state/*.json` para auditoría; si es necesario resetear una feature, usar `flow workflow` comandos de diagnóstico documentados en la spec de la feature (no borrar a ciegas).
5. **Validar**: `python3 ./flow ci integration --profile smoke:ci-clean --auto-up --json` y `python3 -m pytest gateway/tests -q`.
6. **Registrar**: `python3 ./flow ops decision-log add` con decisión, actor y riesgo residual.

## Cuándo escalar

- Fallo persistente en `ci_integration` o DLQ de workflow con reintentos agotados.
- Pérdida de datos en DB del gateway: restaurar backup SQLite/Postgres antes de reanudar tráfico.
