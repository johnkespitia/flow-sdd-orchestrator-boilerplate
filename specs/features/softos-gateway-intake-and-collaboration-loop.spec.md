---
schema_version: 2
name: SoftOS Gateway Intake And Collaboration Loop
description: Unificar intake desde Slack/Jira/GitHub, colaboración del dev y cierre automático del flujo de gateway
status: approved
owner: platform
depends_on:
  - ../../specs/000-foundation/spec-as-source-operating-model.spec.md
  - ../../specs/features/softos-central-spec-registry-and-claiming.spec.md
required_runtimes: []
required_services: []
required_capabilities: []
targets:
  - ../../flow
  - ../../flowctl/**
  - ../../docs/**
  - ../../workspace.providers.json
---

# SoftOS Gateway Intake And Collaboration Loop

## Objetivo

Que el gateway sea la puerta única para requerimientos externos, colaboración humana y notificación de cierre, con trazabilidad fin a fin.

## Alcance

### Incluye

- normalización de eventos Slack/Jira/GitHub a `workflow.intake`
- creación de spec draft central y task asociada
- comentarios bidireccionales reporter↔dev en timeline
- notificaciones por eventos de ciclo de vida
- cierre automático del flujo de gateway cuando `flow` confirme finalización

### Excluye

- bots con lenguaje natural libre sin contrato de intent

## Eventos obligatorios

`created`, `claimed`, `review_requested`, `approved`, `execution_started`, `execution_failed`, `execution_succeeded`, `closed`

## Reglas de negocio

- ningún webhook ejecuta shell arbitrario
- todo evento se traduce a intent permitido
- si falta correlación con spec/task, evento queda en `failed-intake` con causa
- el reporter puede comentar en cualquier estado sin romper lock de implementación

## Criterios de aceptación

- creación desde Jira/GitHub/Slack termina en una spec visible en registro central
- un dev puede tomar, editar, enviar a review y aprobar con eventos notificados
- al completar SDLC desde flow, gateway notifica cierre y marca `closed`
- si ejecución falla, gateway notifica causa y mantiene estado reintentable

## Definición de terminado

- runbook operativo con payloads canónicos de webhooks
- contrato JSON de eventos publicado en `docs/flow-json-contract.md`
- tests E2E de intake->claim->approve->execute->close

