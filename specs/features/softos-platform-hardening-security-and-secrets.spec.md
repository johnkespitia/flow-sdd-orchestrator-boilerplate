---
schema_version: 2
name: SoftOS Platform Hardening Security And Secrets
description: Completar hardening enterprise del gateway y del plano operativo para uso de equipo completo
status: approved
owner: platform
depends_on:
  - ../../specs/features/softos-central-spec-registry-and-claiming.spec.md
  - ../../specs/features/softos-gateway-intake-and-collaboration-loop.spec.md
required_runtimes: []
required_services: []
required_capabilities: []
targets:
  - ../../gateway/**
  - ../../flow
  - ../../flowctl/**
  - ../../workspace.providers.json
  - ../../workspace.secrets.json
  - ../../docs/**
  - ../../TODO.md
---

# SoftOS Platform Hardening Security And Secrets

## Objetivo

Cerrar pendientes de seguridad, resiliencia y operación enterprise para habilitar uso confiable por un equipo completo.

## Alcance

### Incluye

- autenticación robusta y auditoría en intents de gateway
- migración de cola/estado operativo de SQLite a Postgres
- despliegue central del gateway
- integración con secret manager
- validación fuerte de payloads de webhooks
- deduplicación semántica de intake y guardrails anti-spam
- checklist de onboarding operativo

### Excluye

- IAM corporativo específico de un proveedor cloud

## Criterios de aceptación

- intents no autenticados o inválidos son rechazados de forma consistente
- gateway corre en ambiente compartido con persistencia robusta
- secretos no dependen de env locales por usuario
- flujos Jira/GitHub/Slack tienen payload canónico documentado y validado
- dedupe evita intake duplicado por equivalencia semántica

## Definición de terminado

- cumplimiento de los ítems de TODO.md relacionados con seguridad/operación
- runbooks de incidentes, retención y rollback actualizados
- tests E2E de webhooks con fixtures versionados

