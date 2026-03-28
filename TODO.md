# TODO Next Iterations

## Prioridad Alta (Iteración 1)

- [x] Definir y publicar política oficial de aprobación: cuándo va por CLI y cuándo obligatoriamente por gateway.
- [x] Agregar comandos/intents de aprobación por comentario simple en GitHub y Jira sin necesidad de sintaxis larga.
- [x] Añadir tests automáticos para `gateway/app/intents.py` (issues opened/labeled, issue_comment, PR comment, dedup).
- [x] Añadir tests para hidratación de spec desde inbound (`description`, `acceptance_criteria`).
- [ ] Documentar formato canónico de payload para Jira Automation y GitHub Webhooks con ejemplos copy/paste (`docs/webhook-canonical-payloads.md`).
- [ ] Implementar validación fuerte de payload de webhooks con mensajes de error consistentes.

## Prioridad Alta (Iteración 2)

- [ ] Migrar gateway de SQLite local a Postgres (tasks, índices, retención).
- [ ] Crear despliegue central del gateway (ambiente compartido para todo el equipo).
- [ ] Implementar autenticación robusta en `/v1/intents` (token rotativo/JWT) y auditoría por actor.
- [ ] Integrar secretos en un secret manager (no depender de shell/env local por usuario).
- [ ] Definir estrategia de reintentos/backoff para feedback providers externos (Jira/GitHub/Slack).

## CI Smoke Hardening (Pendiente de rollout)

- [ ] `flow ci spec --all` no falla por drafts no aprobadas (aparecen como `status: skipped` con mensaje explícito).
- [ ] Definir y documentar contrato oficial de `smoke:ci-clean` (qué valida y qué bloquea).
- [ ] Hacer obligatorio `flow ci integration --profile smoke:ci-clean` en `root-ci` después de una ventana de adopción.
- [ ] Implementar bootstrap automático opcional para preflight por runtime (ej. `composer install`, `pnpm install`) con flag explícito.
- [ ] Endurecer preflight contracts por runtime en modo estricto por defecto una vez estabilizado el bootstrap.
- [ ] Añadir timeout/backoff configurable por servicio (no solo global) para smoke/health checks.

## Prioridad Media

- [ ] Soportar eventos `pull_request` nativos (opened/edited/labeled) además de `issue_comment`.
- [ ] Evitar intake duplicado por equivalencia semántica (no solo por slug exacto).
- [ ] Incorporar `acceptance_criteria` desde campos Jira custom configurables por `workspace.providers.json`.
- [ ] Agregar guardrails para limitar creación masiva de specs desde spam de comentarios (rate-limit persistente en DB + modo `memory` solo dev).
- [ ] Añadir métrica de latencia y tasa de error por intent/provider.
- [ ] Exponer endpoint de observabilidad (`/metrics`) para gateway.

## Prioridad Media-Baja

- [ ] Diseñar UI mínima de operaciones (task monitor) para ver estado sin consultar DB/reportes manualmente.
- [ ] Permitir reglas de transformación por fuente (Jira/GitHub/Slack) declarativas en config.
- [ ] Agregar plantillas de comentario de feedback por tipo de intent.
- [ ] Revisar estilo y ortografía automática de specs generadas desde inputs externos.

## Deuda Técnica

- [ ] Consolidar pruebas E2E en CI para webhooks reales simulados (fixtures versionados).
- [ ] Reducir acoplamiento entre parseo de intents y construcción de comandos flow.
- [ ] Separar módulo de idempotencia/locking para intake concurrente.
- [ ] Revisar cobertura de `flow secrets scan` para balancear falsos positivos y falsos negativos.

## Operación y Gobernanza

- [ ] Definir SLA de procesamiento de tasks del gateway y políticas de incidentes.
- [ ] Definir política de limpieza/retención para reportes `.flow/reports/**`.
- [ ] Formalizar playbook de rollback para cambios en workflows e integraciones.
- [ ] Añadir checklist de onboarding para nuevos miembros del equipo (tokens, webhooks, smoke tests).
