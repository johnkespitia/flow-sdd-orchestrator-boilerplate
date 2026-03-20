---
name: Spec-Driven Delivery Bootstrap
description: Extender el control plane del workspace para gobernar CI, releases y cambios de infraestructura desde specs del root
status: approved
owner: platform
targets:
  - ../../flow
  - ../../flowctl/**
  - ../../Makefile
  - ../../README.md
  - ../../workspace.config.json
  - ../../workspace.providers.json
  - ../../runtimes/**
  - ../../.github/**
  - ../../docs/spec-driven-sdlc-map.md
  - ../../docs/spec-driven-orchestration.md
  - ../../docs/sdd-implementation-guide.md
  - ../../docs/process-and-integrations-runbook.md
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
- workflows mínimos por repo para proyectos agregados con `flow add-project`
- hooks por defecto de release e infra
- documentación del SDLC resultante
- runbook operativo de integraciones externas (Jira/GitHub/Slack)
- configuración versionada de feedback providers (`workspace.providers.json`)

### Excluye

- despliegues reales a cloud providers
- integración con secretos o plataformas externas
- runners específicos de Terraform/Helm más allá del contrato de hooks

## Criterios de aceptación

- `python3 ./flow ci spec --all` valida el contrato de specs
- `python3 ./flow release cut --version <v> --spec spec-driven-delivery-bootstrap` genera un manifest versionado
- `python3 ./flow release promote --version <v> --env preview` registra una promoción usando el hook por defecto
- `python3 ./flow infra plan spec-driven-delivery-bootstrap --env preview` genera un plan registrable solo para specs aprobadas
- `python3 ./flow infra apply spec-driven-delivery-bootstrap --env preview` ejecuta el hook por defecto y deja evidencia
- `python3 ./flow add-project <repo> --runtime <runtime>` persiste la configuracion CI derivada del runtime y permite overrides por step en el alta
- `python3 ./flow spec approve <spec> --approver <id>` requiere una review previa lista para aprobar
- `python3 ./flow spec create <slug> --runtime <pack> --service <pack> --capability <cap>` genera frontmatter declarativo con `schema_version: 2`
- `python3 ./flow spec review <spec>` y `python3 ./flow ci spec <spec>` fallan si `depends_on`, runtimes, servicios o capabilities declarados no existen o no estan listos
- `python3 ./flow stack design --spec <slug>`, `stack plan --spec <slug>` y `stack apply --spec <slug>` derivan `workspace.stack.json` desde una spec aprobada con `stack_projects`, `stack_services` y `stack_capabilities`
- los runtime packs pueden declarar `bindings` por runtime de servicio para resolver `environment` y `depends_on` sin modificar el core
- las foundation specs generadas por capabilities nacen en `draft`, no en `approved`
- `python3 ./flow release cut --spec <slug>` falla si el plan no existe o si alguna slice planeada no paso verificacion

## Contratos derivados

```json contract
{
  "name": "Release Manifest Envelope",
  "type": "json-schema",
  "repo": "workspace-root",
  "match": [
    "flow"
  ],
  "contains": [
    "def command_release_cut",
    "RELEASE_MANIFEST_ROOT"
  ],
  "schema": {
    "type": "object",
    "required": [
      "version",
      "generated_at",
      "root_sha",
      "repos"
    ]
  }
}
```
