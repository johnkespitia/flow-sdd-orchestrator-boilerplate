---
schema_version: 2
name: SoftOS Program Closure And Operational Readiness
description: Cerrar de forma verificable todos los pendientes activos del backlog operativo para dejar el programa listo para escala de equipo
status: approved
owner: platform
depends_on:
  - ../../specs/000-foundation/spec-as-source-operating-model.spec.md
  - ../../specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - ../../specs/features/softos-gateway-intake-and-collaboration-loop.spec.md
  - ../../specs/features/softos-rollback-retry-and-recovery.spec.md
  - ../../specs/features/softos-observability-sla-and-operations.spec.md
  - ../../specs/features/softos-platform-hardening-security-and-secrets.spec.md
  - ../../specs/features/softos-program-master-plan.spec.md
required_runtimes: []
required_services: []
required_capabilities: []
targets:
  - ../../flow
  - ../../flowctl/**
  - ../../gateway/app/**
  - ../../gateway/tests/**
  - ../../scripts/**
  - ../../docs/**
  - ../../.github/workflows/**
  - ../../workspace.providers.json
  - ../../workspace.secrets.json
---

# SoftOS Program Closure And Operational Readiness

## Objetivo

Cerrar todos los pendientes abiertos del backlog operativo con implementación verificable, evidencia reproducible y gobernanza operativa para ejecución de equipo.

## Contexto

El programa ya tiene capacidades core (intake, engine, locking, quality gates, recovery, observabilidad y hardening base). Falta cerrar backlog operativo para eliminar brechas de adopción, seguridad operativa y consistencia de rollout.

## Foundations aplicables

- `spec-as-source-operating-model`: exige trazabilidad de cambios, evidencia por criterio y estado explícito.
- `spec-driven-delivery-and-infrastructure`: exige comandos de validación y contratos operativos reproducibles.

## Domains aplicables

No aplica spec de dominio (`specs/domains/**`) porque el alcance es plataforma/orquestación y operación de infraestructura de desarrollo.

## Estado base (línea de corte)

Este spec toma como backlog fuente los ítems abiertos del archivo de pendientes operativo en la fecha de aprobación del spec.
Todo ítem agregado después de la aprobación de este spec queda fuera de alcance y deberá ir en un spec nuevo.

## Estado de implementación acumulado

Los cierres operativos ya materializados para esta spec deben quedar reflejados también aquí para mantener alineado el gate de drift sobre superficies estables.

- T22: SLA e incidentes publicados en `docs/gateway-sla-incidents.md`, verificables con `python3 ./flow ops sla --json`.
- T23: retención de `.flow/reports/**` fijada en `docs/flow-reports-retention.md` y validada con `python3 -m pytest -q gateway/tests/test_ola_d.py -k t23`.
- T24: rollback operativo versionado en `docs/playbook-workflow-rollback.md` y validado con `python3 -m pytest -q gateway/tests/test_ola_d.py -k t24`.
- T25: onboarding operativo versionado en `docs/onboarding-team-checklist.md` y validado con `python3 -m pytest -q gateway/tests/test_ola_d.py -k t25`.
- La matriz consolidada `docs/program-closure-evidence-matrix.md` es el artefacto de referencia para `T22..T25` mientras el resto del backlog de cierre siga abierto.

## Precondiciones de entorno

- Python 3.11+ para ejecutar `gateway/tests` completos.
- Dependencias instaladas para gateway y flow.
- Entorno de integración disponible para `smoke:ci-clean`.
- Para rutas Postgres opcionales en tests: variable `SOFTOS_TEST_POSTGRES_URL` definida.

## Problema a resolver

- Existen ítems críticos pendientes en aprobación, webhook intents, smoke hardening, gobernanza operativa y deuda técnica.
- El equipo depende de acuerdos informales para producción/operación en vez de contratos de ejecución cerrados.
- Hay riesgo de regresión por falta de cobertura completa en rutas de gateway/intents e hidratación inbound.

## Alcance

### Incluye

- política oficial CLI vs gateway para aprobación
- intents/comandos de aprobación simple en GitHub/Jira
- cobertura de tests faltantes de intents + hidratación de spec inbound
- despliegue central del gateway y estrategia de reintentos/backoff para feedback providers externos
- cierre de smoke hardening (`smoke:ci-clean` contrato, obligatoriedad, bootstrap por runtime y timeouts por servicio)
- soporte `pull_request` nativo + campos Jira custom para `acceptance_criteria`
- métricas por intent/provider
- reducción de acoplamiento intents->flow command
- módulo explícito de idempotencia/locking intake concurrente
- ajustes de cobertura `flow secrets scan`
- gobernanza operativa: SLA, retención de reportes, playbook rollback, onboarding

### Excluye

- cambios de negocio en productos downstream
- IAM cloud corporativo específico fuera del gateway/workspace
- rediseño completo de arquitectura flow/gateway más allá de los pendientes explícitos del backlog operativo

## Repos afectados

| Repo | Targets |
| --- | --- |
| `sdd-workspace-boilerplate` | `../../flow`, `../../flowctl/**`, `../../gateway/app/**`, `../../gateway/tests/**`, `../../scripts/**`, `../../docs/**`, `../../.github/workflows/**`, `../../workspace.providers.json`, `../../workspace.secrets.json` |

## Plan por olas

### Ola A: Aprobaciones e inbound correctness

- Entregables:
  - política oficial CLI vs gateway en `docs/**` + validación de uso en `flow`/gateway.
  - intents/comandos de aprobación simple para GitHub y Jira (sin sintaxis larga).
  - cobertura de tests para `gateway/app/intents.py` incluyendo `issues opened/labeled`, `issue_comment`, `PR comment`, dedup.
  - hidratación de spec inbound (`description`, `acceptance_criteria`) con tests.
- Archivos esperados:
  - `gateway/app/intents.py`
  - `gateway/tests/test_intents*.py`
  - `docs/**` (política aprobación)
  - `flow` y/o `flowctl/**` (si aplica routing CLI)
- Criterio de salida de ola:
  - sin ítems abiertos del backlog operativo en política/aprobación/intents/hidratación.

### Ola B: Hardening de entrega central

- Entregables:
  - despliegue central gateway documentado y reproducible (scripts + runbook + config).
  - retry/backoff configurable por provider externo (Jira/GitHub/Slack feedback).
  - soporte eventos `pull_request` nativos (`opened/edited/labeled`).
  - ingestión de `acceptance_criteria` desde campos Jira custom configurables.
- Archivos esperados:
  - `gateway/app/main.py`, `gateway/app/feedback.py`, `gateway/app/intents.py`
  - `workspace.providers.json`
  - `scripts/**` (deploy/ops)
  - `docs/**` (runbook central)
- Criterio de salida de ola:
  - sin ítems abiertos del backlog operativo en despliegue central/retry externos/PR/Jira custom.

### Ola C: CI smoke hardening end-to-end

- Entregables:
  - contrato oficial `smoke:ci-clean` con alcance y bloqueos.
  - enforcement en `root-ci` tras ventana definida.
  - bootstrap opcional por runtime (flag explícito).
  - preflight contracts por runtime en modo estricto por defecto.
  - timeout/backoff por servicio para smoke/health.
- Archivos esperados:
  - `.github/workflows/**`
  - `flow`, `flowctl/ci.py`, `flowctl/workspace_ops.py` (o equivalentes)
  - `docs/**` (contrato de smoke)
- Criterio de salida de ola:
  - sin ítems abiertos del backlog operativo en smoke hardening.

### Ola D: Operación y deuda técnica

- Entregables:
  - métricas latencia/error por intent/provider en observabilidad.
  - separación de responsabilidades parseo intents vs command builder.
  - módulo explícito de idempotencia/locking de intake concurrente.
  - revisión de `flow secrets scan` con criterios de precisión documentados.
  - SLA de procesamiento y políticas de incidentes.
  - política de retención/limpieza `.flow/reports/**`.
  - playbook formal de rollback workflow/integraciones.
  - checklist onboarding operativo.
- Archivos esperados:
  - `flowctl/operations.py`, `gateway/app/**`, `flowctl/**`
  - `docs/**`
  - archivo de pendientes operativo
- Criterio de salida de ola:
  - sin ítems abiertos del backlog operativo en observabilidad, deuda técnica y gobernanza.

## Mapeo explícito backlog -> entregable

| ID | Línea del backlog | Pendiente | Entregable mínimo verificable |
| --- | --- | --- | --- |
| T01 | 5 | Política CLI vs gateway | Documento versionado + referencia desde runbook + regla de enforcement |
| T02 | 6 | Aprobación simple GitHub/Jira | Intent/comando implementado + tests |
| T03 | 7 | Tests intents.py | Suite dedicada para eventos listados |
| T04 | 8 | Hidratación inbound | Tests que validen `description` y `acceptance_criteria` |
| T05 | 15 | Despliegue central gateway | Script/runbook reproducible en entorno compartido |
| T06 | 18 | Retry/backoff providers externos | Política configurable + pruebas de reintento |
| T07 | 23 | Contrato smoke:ci-clean | Doc con alcance/bloqueos + ejemplo de salida |
| T08 | 24 | Smoke obligatorio en root-ci | Workflow actualizado con gating |
| T09 | 25 | Bootstrap opcional por runtime | Flag CLI + docs + tests |
| T10 | 26 | Preflight estricto runtime | Modo estricto default + bypass controlado |
| T11 | 27 | Timeout/backoff por servicio | Config por servicio + evidencia smoke |
| T12 | 31 | pull_request nativo | Routing/parseo + tests |
| T13 | 33 | Jira custom acceptance_criteria | Config en providers + test de hidratación |
| T14 | 35 | Métrica latencia/error intent/provider | Métrica visible en reports/metrics |
| T15 | 40 | UI mínima operaciones | Pantalla o vista mínima documentada/usable |
| T16 | 41 | Reglas transform declarativas | Config + loader + test |
| T17 | 42 | Plantillas feedback | Plantillas por intent + tests |
| T18 | 43 | Estilo/ortografía specs | Paso automático + report |
| T19 | 48 | Desacoplar parseo vs comandos | Refactor con módulos separados + tests |
| T20 | 49 | Módulo idempotencia/locking intake | Módulo dedicado + concurrencia test |
| T21 | 50 | Ajuste flow secrets scan | Métricas de precisión + reglas actualizadas |
| T22 | 54 | SLA tasks + incidentes | Política SLA + runbook incidentes |
| T23 | 55 | Retención .flow/reports | Política + job/script limpieza |
| T24 | 56 | Playbook rollback workflows | Documento operativo paso a paso |
| T25 | 57 | Onboarding equipo | Checklist operativo completo |

## Criterios de aceptación

1. Cada ítem T01..T25 tiene evidencia explícita de cierre (archivo + test/comando) o justificación `no aplica` aprobada.
2. El archivo de pendientes operativo queda actualizado sin marcar `[x]` ítems parciales.
3. `python3 -m pytest gateway/tests -q` pasa en Python 3.11+ sin skips por compatibilidad de runtime.
4. `flow ci spec --all --json`, `flow ci repo --all --json` y `flow ci integration --profile smoke:ci-clean --auto-up --json` pasan.
5. Se publica contrato de smoke oficial y enforcement de root CI activo.
6. Se publican runbooks de operación: SLA/incidentes, rollback, retención de reportes, onboarding.

## Contratos operativos obligatorios

- Contrato de aprobación:
  - entrada: comentario o comando de aprobación (CLI/Gateway)
  - salida: intent canónico + audit trail
  - error: respuesta determinística con `code` y `message`
- Contrato de smoke:
  - checks mínimos obligatorios por categoría
  - criterios PASS/FAIL documentados
  - política de timeout/backoff por servicio
- Contrato de observabilidad:
  - métricas por intent/provider incluyen al menos `count`, `failure_rate`, `p95_latency`
  - reportes persistidos en `.flow/reports/**`

## Evidencia obligatoria

```bash
python3 -V
python3 -m pytest gateway/tests -q
python3 ./flow ci spec --all --json
python3 ./flow ci repo --all --json
python3 ./flow ci integration --profile smoke:ci-clean --auto-up --json
python3 ./flow ops metrics --json
python3 ./flow ops dashboard --json
python3 ./flow ops sla --json
python3 ./flow ops decision-log list --limit 20 --json
```

Adjuntar:

- diffs del archivo de pendientes operativo mostrando cierre real T01..T25
- reportes en `.flow/reports/**`
- tabla `Txx -> archivo -> test/comando -> resultado`
- matriz versionada en `docs/program-closure-evidence-matrix.md` para ítems ya cerrados
- evidencia de root CI con smoke obligatorio
- evidencia de runbook de despliegue central gateway

## Matriz mínima de pruebas

- Unit tests:
  - intents parse/routing
  - hidratación inbound
  - retry/backoff providers
  - idempotencia/locking intake
  - transform rules por fuente
- Integration tests:
  - webhooks E2E con fixtures versionados
  - smoke:ci-clean con bootstrap opcional
  - secrets scan con set de casos controlado
- Operación:
  - ejecución de runbooks (rollback, incidentes, onboarding) validada en dry-run

## Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación requerida |
| --- | --- | --- |
| Entornos inconsistentes (3.9 vs 3.11) | falsos fallos de tests | pin de runtime en CI/docs + validación de versión |
| Smoke demasiado estricto | bloqueos de entrega | ventana de adopción + feature flags de bootstrap |
| Rate-limit/locking regressions | pérdida de intake válido | tests de concurrencia + canary en gateway central |
| Secrets scan con ruido | baja adopción | calibración con dataset real y umbrales documentados |

## Rollout

1. Merge por olas A->B->C->D (un PR por ola).
2. Cada PR incluye matriz `Txx` cerrada para su ola.
3. Ventana de adopción de smoke en modo warning antes de modo blocking.
4. Activación gradual runtime strict con fallback explícito.

## Rollback

- revertir enforcement smoke a modo informativo si supera umbral de fallo acordado
- desactivar temporalmente runtime strict por flag documentado
- rollback de gateway central a configuración previa estable
- conservar bitácora de decisiones y alertas durante rollback

## Definición de terminado

- T01..T25 cerrados o justificados como `no aplica` con aprobación explícita
- archivo de pendientes operativo actualizado y consistente con evidencia
- CI completo en verde en entorno objetivo
- documentación operativa y de gobernanza publicada
- sin bloqueos P0/P1 para siguiente ola del master plan
