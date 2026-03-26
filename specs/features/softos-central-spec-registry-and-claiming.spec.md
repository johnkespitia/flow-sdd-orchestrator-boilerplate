---
schema_version: 2
name: SoftOS Central Spec Registry And Claiming
description: Centralizar specs y evitar implementación duplicada mediante claim/lock con trazabilidad completa
status: approved
owner: platform
depends_on:
  - ../../specs/000-foundation/spec-as-source-operating-model.spec.md
  - ../../specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - ../../specs/features/spec-driven-delivery-bootstrap.spec.md
required_runtimes: []
required_services: []
required_capabilities: []
targets:
  - ../../gateway/**
  - ../../flow
  - ../../flowctl/**
  - ../../workspace.config.json
  - ../../workspace.providers.json
  - ../../docs/**
  - ../../specs/features/**
---

# SoftOS Central Spec Registry And Claiming

## Objetivo

Implementar un registro central de specs con ownership transaccional para que una spec no pueda ser ejecutada por dos desarrolladores/agentes al mismo tiempo.

## Alcance

### Incluye

- entidad central `spec_registry` con estados y auditoría
- comando/intento `claim spec` con TTL + heartbeat
- desbloqueo automático por expiración
- rechazo explícito de doble claim
- timeline completo de cambios de estado y actor

### Excluye

- UI avanzada (solo endpoints + payloads listos para UI)
- asignación automática por carga (se cubre en spec de scheduler)

## Consideración de dominio

No existen specs de dominio funcional en `specs/domains/**` (solo README). Esta spec aplica al dominio transversal de orquestación del SDLC.

## Estados mínimos obligatorios

`new -> triaged -> in_edit -> in_review -> approved -> in_execution -> in_validation -> done -> closed`

Reglas:

- solo un `assignee` activo en `in_edit` o `in_execution`
- transición inválida debe fallar con error determinístico
- cada transición guarda `actor`, `reason`, `timestamp`, `source` (cli/gateway/webhook)

## Contrato API mínimo

- `POST /v1/specs/{id}/claim`
- `POST /v1/specs/{id}/heartbeat`
- `POST /v1/specs/{id}/release`
- `POST /v1/specs/{id}/transition`
- `GET /v1/specs/{id}`
- `GET /v1/specs?state=...&assignee=...`

## Criterios de aceptación

- dos claims concurrentes sobre la misma spec: solo uno debe ganar
- expirado el TTL sin heartbeat, otro actor puede tomar la spec
- el registro de auditoría conserva todas las transiciones en orden
- `flow status <slug> --json` y gateway exponen el mismo estado lógico
- cada transición inválida devuelve error explícito y no altera estado

## Definición de terminado

- contrato de estado documentado en `docs/`
- comandos/intent reproducibles con ejemplos curl y flow
- cobertura de tests de concurrencia para claim/release/heartbeat

