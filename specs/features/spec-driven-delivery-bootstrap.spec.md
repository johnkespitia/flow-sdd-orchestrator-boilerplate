---
name: Spec-Driven Delivery Bootstrap
description: Extender el control plane del workspace para gobernar CI, releases y cambios de infraestructura desde specs del root
status: approved
owner: platform
targets:
  - ../../flow
  - ../../Makefile
  - ../../README.md
  - ../../workspace.config.json
  - ../../.github/**
  - ../../backend/.github/**
  - ../../frontend/.github/**
  - ../../docs/spec-driven-sdlc-map.md
  - ../../docs/spec-driven-orchestration.md
  - ../../docs/sdd-implementation-guide.md
  - ../../specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - ../../specs/features/spec-driven-delivery-bootstrap.spec.md
  - ../../scripts/release/**
  - ../../scripts/infra/**
infra_targets:
  - ../../.devcontainer/**
  - ../../scripts/infra/**
---

# Spec-Driven Delivery Bootstrap

## Objetivo

Bootstrappear el workspace para que el mismo control plane pueda ejecutar:

- CI gobernado por specs
- corte de manifests y promociones de release
- y planes/applies de infraestructura bajo hooks versionados

## Alcance

### Incluye

- subcomandos `flow ci`
- subcomandos `flow release`
- subcomandos `flow infra`
- workflows del root para CI, release e infra
- workflows mínimos por repo para backend y frontend
- hooks por defecto de release e infra
- documentación del SDLC resultante

### Excluye

- despliegues reales a cloud providers
- integración con secretos o plataformas externas
- runners específicos de Terraform/Helm más allá del contrato de hooks

## Criterios de aceptación

- `python3 ./flow ci spec --all` valida el contrato de specs
- `python3 ./flow release cut --version <v> --spec spec-driven-delivery-bootstrap` genera un manifest versionado
- `python3 ./flow release promote --version <v> --env preview` registra una promoción usando el hook por defecto
- `python3 ./flow infra plan spec-driven-delivery-bootstrap --env preview` genera un plan registrable
- `python3 ./flow infra apply spec-driven-delivery-bootstrap --env preview` ejecuta el hook por defecto y deja evidencia
- `backend` y `frontend` exponen CI mínimo reproducible aunque todavía sean placeholders
