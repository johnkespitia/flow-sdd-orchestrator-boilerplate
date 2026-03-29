---
schema_version: 2
name: SoftOS Autonomous SDLC Execution Engine
description: Ejecutar automáticamente el SDLC desde specs aprobadas con checkpoints, callbacks y estado consistente
status: released
owner: platform
depends_on:
  - ../../specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - ../../specs/features/spec-driven-delivery-bootstrap.spec.md
  - ../../specs/features/softos-central-spec-registry-and-claiming.spec.md
required_runtimes: []
required_services: []
required_capabilities: []
targets:
  - ../../flow
  - ../../flowctl/**
  - ../../docs/**
---

# SoftOS Autonomous SDLC Execution Engine

## Objetivo

Pasar de “workflow sugerido” a ejecución automática controlada por estado para todo el SDLC, desde spec aprobada hasta confirmación de cierre.

## Alcance

### Incluye

- engine de etapas con máquina de estados
- etapas mínimas: `plan`, `slice_start`, `ci_spec`, `ci_repo`, `ci_integration`, `release_promote`, `release_verify`, `infra_apply`
- callbacks de progreso hacia gateway
- pause/resume/retry por etapa
- bloqueo de avance si un checkpoint falla

### Excluye

- auto-merge sin políticas de riesgo (cubierto por spec de gobernanza)

## Contrato de etapa

Cada etapa debe registrar:

- `stage_name`
- `started_at`, `finished_at`
- `status` (`started/passed/failed/skipped`)
- `input_ref`, `output_ref`
- `attempt`
- `failure_reason` (si aplica)

## Criterios de aceptación

- al aprobar una spec, engine puede ejecutarla sin intervención manual paso a paso
- cada etapa deja reporte legible y JSON en `.flow/reports/**`
- un fallo en etapa no deja workflow inconsistente
- gateway recibe callbacks de inicio/avance/fallo/cierre
- reintento de etapa mantiene idempotencia de estado

## Definición de terminado

- comando único `flow workflow run <slug> --json` (o equivalente) para ejecución completa
- documentación de stage contract y códigos de error
- pruebas de happy path y fallos por etapa

