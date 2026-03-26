---
schema_version: 2
name: SoftOS Program Master Plan
description: Plan maestro ejecutable para completar el ciclo autónomo de SoftOS en olas implementables sin ambigüedad
status: approved
owner: platform
depends_on:
  - ../../specs/000-foundation/spec-as-source-operating-model.spec.md
  - ../../specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - ../../specs/features/spec-driven-delivery-bootstrap.spec.md
  - ../../specs/features/softos-central-spec-registry-and-claiming.spec.md
  - ../../specs/features/softos-gateway-intake-and-collaboration-loop.spec.md
  - ../../specs/features/softos-autonomous-sdlc-execution-engine.spec.md
  - ../../specs/features/softos-multiagent-concurrency-and-locking.spec.md
  - ../../specs/features/softos-quality-gates-traceability-and-risk.spec.md
  - ../../specs/features/softos-rollback-retry-and-recovery.spec.md
  - ../../specs/features/softos-observability-sla-and-operations.spec.md
  - ../../specs/features/softos-platform-hardening-security-and-secrets.spec.md
required_runtimes: []
required_services: []
required_capabilities: []
targets:
  - ../../gateway/**
  - ../../flow
  - ../../flowctl/**
  - ../../docs/**
  - ../../specs/**
  - ../../TODO.md
---

# SoftOS Program Master Plan

## Objetivo

Definir el orden exacto de implementación, pruebas y rollout para completar el SoftOS autónomo para un equipo completo.

## Consideración de dominio

No hay specs de dominio en `specs/domains/**`. El alcance de este programa es plataforma/orquestación.

## Reglas de ejecución para implementadores

- Implementar en orden de olas (no saltar olas).
- Cada ola debe cerrar con: `ci spec`, `ci repo`, `ci integration` y reporte de evidencia.
- No mezclar cambios de dos olas en un mismo PR.
- Si un criterio de aceptación falla, no avanzar de ola.

## Olas de implementación

## Ola 1: Registro central y loop de colaboración

Specs:

- `softos-central-spec-registry-and-claiming`
- `softos-gateway-intake-and-collaboration-loop`

Implementar:

- modelo de datos de specs/tareas central
- claim/release/heartbeat
- timeline de eventos y comentarios
- notificaciones de lifecycle desde gateway

Evidencia obligatoria:

```bash
python3 ./flow doctor
python3 ./flow workflow doctor --json
python3 ./flow ci spec --all
python3 ./flow ci repo --all --json
```

## Ola 2: Ejecución autónoma SDLC

Specs:

- `softos-autonomous-sdlc-execution-engine`

Implementar:

- stage engine con estado persistente por etapa
- callbacks `stage_started|stage_passed|stage_failed|finalized`
- reintento por etapa e idempotencia

Evidencia obligatoria:

```bash
python3 ./flow workflow next-step <slug> --json
python3 ./flow workflow execute-feature <slug> --start-slices --json
python3 ./flow status <slug> --json
```

## Ola 3: Paralelismo seguro multiagente

Specs:

- `softos-multiagent-concurrency-and-locking`

Implementar:

- workers paralelos
- scheduler por capacidad de repo/área caliente
- preflight de conflicto por archivos reales
- DAG de slices y locks semánticos
- DLQ

Evidencia obligatoria:

```bash
python3 ./flow ci integration --profile smoke --json
python3 ./flow ci integration --profile smoke:ci-clean --auto-up --json
```

## Ola 4: Calidad, riesgo y trazabilidad

Specs:

- `softos-quality-gates-traceability-and-risk`

Implementar:

- checkpoints por etapa
- matriz automática `spec->slice->commit->test->release`
- score de confianza por slice
- gates adaptativos por riesgo
- enforcement fuerte de contracts API/DTO

Evidencia obligatoria:

```bash
python3 ./flow spec generate-contracts <slug> --json
python3 ./flow contract verify --all --json
python3 ./flow drift check --all --json
```

## Ola 5: Recovery y rollback transaccional

Specs:

- `softos-rollback-retry-and-recovery`

Implementar:

- retry policy por tipo de error
- rollback por etapa con compensaciones
- reasignación tras fallos agotados

Evidencia obligatoria:

```bash
python3 ./flow release promote --version <v> --env preview --json
python3 ./flow release verify --version <v> --env preview --json
python3 ./flow status <slug> --json
```

## Ola 6: Observabilidad y SLA

Specs:

- `softos-observability-sla-and-operations`

Implementar:

- `/metrics`
- tablero de runs
- SLA por etapa y alertas
- bitácora de decisiones

Evidencia obligatoria:

- dashboard con filtros por spec/repo/actor
- alertas de SLA violado con prueba de disparo

## Ola 7: Hardening enterprise

Specs:

- `softos-platform-hardening-security-and-secrets`

Implementar:

- auth fuerte + auditoría en intents
- migración SQLite -> Postgres
- despliegue central gateway
- secret manager
- validación fuerte payloads + dedupe semántico + anti-spam

Evidencia obligatoria:

```bash
python3 ./flow ci spec --all
python3 ./flow ci repo --all --json
python3 ./flow ci integration --profile smoke:ci-clean --auto-up --json
```

## Matriz TODO.md -> Specs

- Política aprobación CLI/Gateway -> `softos-gateway-intake-and-collaboration-loop`
- Comandos/intents aprobación en GitHub/Jira -> `softos-gateway-intake-and-collaboration-loop`
- Tests gateway intents/hidratación -> `softos-platform-hardening-security-and-secrets`
- Payload canónico webhooks -> `softos-gateway-intake-and-collaboration-loop`
- Validación fuerte webhooks -> `softos-platform-hardening-security-and-secrets`
- Migración a Postgres -> `softos-platform-hardening-security-and-secrets`
- Despliegue central gateway -> `softos-platform-hardening-security-and-secrets`
- Auth robusta/auditoría -> `softos-platform-hardening-security-and-secrets`
- Secret manager -> `softos-platform-hardening-security-and-secrets`
- Retry/backoff providers externos -> `softos-rollback-retry-and-recovery`
- Dedupe semántico/anti-spam -> `softos-platform-hardening-security-and-secrets`
- Métricas y `/metrics` -> `softos-observability-sla-and-operations`
- SLA/incidentes/retención/playbook rollback -> `softos-observability-sla-and-operations`
- Idempotencia/locking intake concurrente -> `softos-central-spec-registry-and-claiming` + `softos-multiagent-concurrency-and-locking`
- CI smoke hardening/`smoke:ci-clean` -> `softos-multiagent-concurrency-and-locking` + `softos-quality-gates-traceability-and-risk`

## Checklist literal para implementadores junior

Aplicar esta secuencia exacta por cada spec:

1. Crear branch `feature/<slug-spec>`.
2. Implementar solo archivos incluidos en `targets`.
3. Ejecutar siempre:
   - `python3 ./flow ci spec --all`
   - `python3 ./flow ci repo --all --json`
   - `python3 ./flow ci integration --profile smoke --json`
4. Si toca API/DTO, ejecutar además:
   - `python3 ./flow spec generate-contracts <slug> --json`
   - `python3 ./flow contract verify --all --json`
5. Adjuntar en PR:
   - comandos ejecutados
   - reportes `.flow/reports/**`
   - decisiones y tradeoffs
6. No pasar a la siguiente ola hasta merge de la actual.

Checklist mínimo por spec:

- `softos-central-spec-registry-and-claiming`: modelo de datos + endpoints claim/release/heartbeat + tests de concurrencia.
- `softos-gateway-intake-and-collaboration-loop`: normalización webhooks + timeline + notificaciones de lifecycle + cierre por callback.
- `softos-autonomous-sdlc-execution-engine`: stage engine + persistencia de etapas + callbacks + pause/resume/retry.
- `softos-multiagent-concurrency-and-locking`: workers paralelos + scheduler + preflight conflicto + DAG + locks semánticos + DLQ.
- `softos-quality-gates-traceability-and-risk`: checkpoints por etapa + matriz trazabilidad + score + gates por riesgo.
- `softos-rollback-retry-and-recovery`: retry policy + rollback por etapa + compensaciones + reasignación segura.
- `softos-observability-sla-and-operations`: métricas + dashboard + SLA + alertas + bitácora.
- `softos-platform-hardening-security-and-secrets`: auth/audit gateway + Postgres + secret manager + validación payload + dedupe + anti-spam.

## Definición de terminado del programa

- todas las olas implementadas y aprobadas
- gateway y flow sincronizados por eventos de ciclo de vida
- cierre automático de spec con notificación externa verificable
- evidencia operativa y de calidad disponible sin intervención manual
