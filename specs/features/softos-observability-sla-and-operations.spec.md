---
schema_version: 2
name: SoftOS Observability SLA And Operations
description: Proveer observabilidad operativa completa del orquestador multiagente con SLA por etapa y alertas
status: approved
owner: platform
depends_on:
  - ../../specs/000-foundation/spec-as-source-operating-model.spec.md
  - ../../specs/features/softos-autonomous-sdlc-execution-engine.spec.md
required_runtimes: []
required_services: []
required_capabilities: []
targets:
  - ../../flow
  - ../../flowctl/**
  - ../../docs/**
---

# SoftOS Observability SLA And Operations

## Objetivo

Operar SoftOS como plataforma para equipo completo, con métricas, tablero único de runs, alertas y SLAs por etapa.

## Alcance

### Incluye

- endpoint de métricas operativas (`/metrics`)
- tablero de runs con estados, bloqueos, tiempos y cuellos de botella
- SLA por etapa con alertas cuando se exceden umbrales
- reporte de incidentes y bitácora de decisiones agente-humano

### Excluye

- BI histórico complejo fuera del dominio operativo

## Criterios de aceptación

- se puede observar en tiempo real qué está corriendo, qué está bloqueado y por qué
- alertas diferenciadas por severidad/etapa
- MTTR y tiempos por etapa disponibles para análisis semanal
- decisiones clave quedan registradas con contexto y actor

## Definición de terminado

- runbook de operación y triage actualizado
- dashboard con filtros por spec/repo/actor/estado
- métricas mínimas: throughput, tasa de fallo, latencia por etapa, retries, DLQ

