---
name: Spec-Driven Delivery And Infrastructure
description: Contrato operativo para extender Spec As Source a CI, release y cambios de infraestructura
status: approved
owner: platform
targets:
  - ../../flow
  - ../../Makefile
  - ../../README.md
  - ../../docs/spec-driven-orchestration.md
  - ../../docs/spec-driven-sdlc-map.md
  - ../../.github/**
  - ../../specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
---

# Spec-Driven Delivery And Infrastructure

## Objetivo

Extender el workspace para que la misma spec del root gobierne:

- validación en CI
- cortes de release y promociones
- y cambios de infraestructura

## Reglas

- Ningún cambio de comportamiento entra a CI sin una spec del root válida.
- Ningún release promueve submódulos sueltos; se promueve el snapshot completo definido por el root.
- Ningún cambio de infraestructura se aplica fuera de una spec que declare `infra_targets`.
- Los comandos operativos de CI, release e infra entran por `flow`, no por scripts sueltos.

## Capas

### CI

`flow ci` debe cubrir:

- validación estructural de specs
- validación por repo afectado
- smoke checks del stack
- en modo `--changed`, resolver un `base` válido para evitar fallas por rangos Git inválidos (si `before` no existe, usar fallback al parent de `head`)

### Release

`flow release` debe cubrir:

- corte de manifest
- consulta del manifest
- estado de promociones
- promoción por entorno

### Infraestructura

`flow infra` debe cubrir:

- generación de plan
- apply gobernado por gates
- trazabilidad de plan y apply por feature y entorno

## Artefactos requeridos

### Reportes de CI

- `.flow/reports/ci/**`

### Reportes de infraestructura

- `.flow/reports/infra/**`

### Releases

- `releases/manifests/**`
- `releases/promotions/**`

## Gates

### Humanos

1. `spec-approved`
2. `plan-approved`
3. `merge-approved`
4. `staging-approved`
5. `production-approved`

### Automáticos

- validación de frontmatter
- validación de `targets`
- validación de `[@test]`
- CI de repo
- smoke checks de integración
- validación de manifest
- validación de plan de infraestructura

## Orden de promoción

1. merge del submódulo afectado
2. actualización del puntero del submódulo en el root
3. corte de release desde el root
4. promoción a `preview`
5. promoción a `staging`
6. promoción a `production`

## Regla de infraestructura

Si una feature afecta infraestructura, la spec debe declarar `infra_targets` y la ejecución debe
quedar registrada por entorno.
