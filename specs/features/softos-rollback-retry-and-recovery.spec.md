---
schema_version: 2
name: SoftOS Rollback Retry And Recovery
description: Introducir ejecución transaccional con retry por tipo de falla, rollback operativo y reasignación segura
status: approved
owner: platform
depends_on:
  - ../../specs/features/softos-autonomous-sdlc-execution-engine.spec.md
  - ../../specs/features/softos-multiagent-concurrency-and-locking.spec.md
required_runtimes: []
required_services: []
required_capabilities: []
targets:
  - ../../flow
  - ../../flowctl/**
  - ../../gateway/**
  - ../../docs/**
---

# SoftOS Rollback Retry And Recovery

## Objetivo

Evitar workflows corruptos o “a medias” cuando una etapa falla.

## Alcance

### Incluye

- política estándar de retry por categoría de error (infra, dependencia, validación, lógica)
- rollback operativo por etapa
- compensaciones para side-effects (estado, reportes, promoción parcial)
- reasignación automática/manual tras fallos agotados

### Excluye

- rollback de negocio dentro de sistemas externos no controlados por provider

## Reglas obligatorias

- cada etapa define operaciones compensables y no compensables
- agotados retries, la tarea pasa a DLQ con contexto completo
- reasignación no puede perder auditoría previa

## Criterios de aceptación

- fallo de CI/smoke/release deja estado consistente y reintentable
- rollback restaura estado y evita avance de etapas dependientes
- reportes explican claramente qué se revirtió y qué quedó pendiente

## Definición de terminado

- tabla de retry/rollback por tipo de falla
- playbook de recuperación en docs
- tests de fallos transitorios y permanentes

