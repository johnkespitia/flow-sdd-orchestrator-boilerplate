---
schema_version: 2
name: SoftOS Quality Gates Traceability And Risk
description: Endurecer gobernanza con checkpoints por etapa, matriz de trazabilidad completa y gates adaptativos por riesgo
status: approved
owner: platform
depends_on:
  - ../../specs/features/softos-autonomous-sdlc-execution-engine.spec.md
required_runtimes: []
required_services: []
required_capabilities: []
targets:
  - ../../flow
  - ../../flowctl/**
  - ../../docs/**
  - ../../contracts/**
  - ../../specs/**
---

# SoftOS Quality Gates Traceability And Risk

## Objetivo

Asegurar que cada etapa del SDLC deje evidencia verificable y que los gates aumenten automáticamente según impacto/riesgo.

## Alcance

### Incluye

- checkpoints obligatorios por etapa multiagente
- matriz automática `spec -> slice -> commit -> test -> release`
- validación contractual estricta para cambios API/DTO
- score de confianza por slice
- política de gates adaptativa por riesgo (`low/medium/high/critical`)

### Excluye

- scoring basado en IA generativa no determinística

## Reglas obligatorias

- si cambia API/DTO: debe actualizar `json contract` y pasar `generate-contracts`
- specs de riesgo `high/critical` requieren validaciones extras (`ci integration` extendido + reviewer adicional)
- no se permite promoción de release si score < umbral definido por entorno

## Criterios de aceptación

- cada run genera matriz trazable consumible por humanos y máquinas
- score de confianza influye el avance automático de etapa
- reglas de riesgo quedan versionadas y auditables
- cualquier bypass queda explícitamente registrado con actor y motivo

## Definición de terminado

- tabla de umbrales por entorno en docs
- reporte de calidad por slice y por feature
- tests de enforcement para contratos y riesgo

