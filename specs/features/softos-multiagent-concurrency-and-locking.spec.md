---
schema_version: 2
name: SoftOS Multiagent Concurrency And Locking
description: Habilitar ejecución paralela segura con workers, scheduler por capacidad, DAG de slices y locks semánticos
status: approved
owner: platform
depends_on:
  - ../../specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - ../../specs/features/softos-autonomous-sdlc-execution-engine.spec.md
required_runtimes: []
required_services: []
required_capabilities: []
targets:
  - ../../flow
  - ../../flowctl/**
  - ../../docs/**
---

# SoftOS Multiagent Concurrency And Locking

## Objetivo

Permitir multiagente real sin corrupción de cambios ni trabajo duplicado.

## Alcance

### Incluye

- cola de trabajo paralela con workers
- scheduler con capacidad por repo/área caliente
- preflight de conflictos por archivos reales antes de ejecutar slices
- DAG de slices (`depends_on`)
- locks semánticos temporales para migraciones/rutas API/contratos
- dead-letter queue para tareas fallidas permanentes

### Excluye

- auto-resolución inteligente de conflictos de merge

## Reglas obligatorias

- dos slices con solapamiento crítico no pueden correr en paralelo
- una slice bloqueada por dependencia no debe consumir reintentos inútiles
- todo lock debe tener TTL y razón de bloqueo

## Criterios de aceptación

- N workers procesan tareas en paralelo sin duplicación
- colisión detectada en preflight bloquea ejecución insegura con mensaje explícito
- dependencia de DAG evita ejecución prematura de slices
- dead-letter captura fallos agotados y preserva contexto

## Definición de terminado

- reportes de scheduler (cola, capacidad, waits, locks)
- tests de concurrencia y carreras reproducibles
- documentación de política de locks y prioridad de colas

