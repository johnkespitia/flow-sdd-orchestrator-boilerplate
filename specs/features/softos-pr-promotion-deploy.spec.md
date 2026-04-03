---
schema_version: 3
name: "SoftOS PR Promotion Deploy & Schema Sync Contract"
description: "Convertir PR-based promotion deploy y schema-sync migrations por tabla en capacidades reutilizables de SoftOS mediante provider parametrizable, workflows template, runbook operativo y contrato estándar de schema-sync."
status: approved
owner: platform
single_slice_reason: ""
multi_domain: false
phases: []
depends_on:
  - specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - specs/000-foundation/spec-as-source-operating-model.spec.md
  - specs/features/spec-driven-delivery-bootstrap.spec.md
required_runtimes:
  - python
required_services: []
required_capabilities: []
stack_projects: []
stack_services: []
stack_capabilities: []
targets:
  - ../../scripts/providers/release/github_actions.sh
  - ../../templates/github-workflows/promotion-pr.yml
  - ../../templates/github-workflows/deploy-on-pr-merge.yml
  - ../../templates/github-workflows/promotion-pr-ci.yml
  - ../../docs/softos-pr-promotion-runbook.md
  - ../../workspace.providers.json
  - ../../workspace.config.json
  - ../../specs/features/softos-pr-promotion-deploy.spec.md
---

# SoftOS PR Promotion Deploy & Schema Sync Contract

## Objetivo

Estandarizar en SoftOS un patrón reusable para:

- promotion deploy basado en PR (`staging` / `main`);
- `main` como rama terminal de producción;
- deploy condicionado al merge del PR con guardrails operativos;
- release provider `github-actions` parametrizable por repo y entorno;
- runbook de branch protection y checks críticos;
- contrato estándar de schema-sync por tabla para derivados que extraen baseline desde dumps SQL.

## Contexto

En derivados ya existe un patrón funcional de:

- crear PRs de promoción entre ramas de entorno;
- desplegar cuando el PR se mergea;
- aplicar guardrails de path, aislamiento de `.env`/`storage`, release marker y healthcheck;
- y sincronizar schema legacy desde un dump SQL.

Ese valor todavía no estaba modelado en SoftOS como una capacidad reusable y parametrizable de boilerplate.

## Alcance

### Incluye

- template reusable `promotion-pr.yml`;
- template reusable `deploy-on-pr-merge.yml`;
- template reusable `promotion-pr-ci.yml`;
- provider `github-actions` parametrizable desde `workspace.config.json` / `workspace.providers.json`;
- runbook operativo de promotion deploy;
- contrato estándar de schema-sync por tabla para specs derivadas.

### No incluye

- un deploy real acoplado a un hosting específico;
- secretos/productive credentials;
- una implementación concreta del parser/generador de migraciones por tabla para un derivado específico.

## Resultado esperado

- SoftOS provee un patrón reusable de promotion deploy por PR sin acoplarse a un repositorio puntual.
- Los derivados pueden configurar repo/ref/source_ref/run_migrations por entorno sin tocar el core.
- El boilerplate no debe sugerir `main -> staging`; la promoción final debe cerrar `staging -> main`.
- SoftOS publica un runbook genérico para branch protection, checks requeridos, promote/verify/rollback.
- Las specs de schema-sync en derivados tienen un contrato estándar que evita planes ambiguos o incompletos.

## Reglas

- El workflow `promotion-pr.yml` se dispara solo por `workflow_dispatch`.
- El workflow `deploy-on-pr-merge.yml` se dispara solo en `pull_request.closed` y solo continúa si `merged == true`.
- `main` es la rama terminal de producción en el patrón por defecto del boilerplate.
- `staging` no puede usar `main` como rama fuente por defecto.
- `production` solo puede promoverse desde `staging`.
- `staging` y `production` usan guardrails de path y aislamiento antes del deploy.
- El release provider `github-actions` traduce `environment`, `version`, `source_ref`, `requested_by` y `run_migrations` al workflow hijo.
- `flow release promote` debe heredar autenticación GitHub hacia el provider reusable; si solo existe `SOFTOS_GITHUB_TOKEN`, el provider debe normalizarlo a `GH_TOKEN`.
- El contrato de schema-sync exige exactamente una migración por `CREATE TABLE` del dump, excepto `migrations`.
- La vista va separada del DDL de tablas.
- Los tests de schema-sync deben cubrir paridad local y verificación estructural en MySQL CI usando `information_schema`.

## Contracto estándar de schema-sync

Una spec derivada de schema-sync debe exigir como mínimo:

1. exactamente un archivo de migración por cada `CREATE TABLE` del dump, excepto `migrations`;
2. DDL de tablas versionado en `schema/ddl/tables/<table>.sql`;
3. vistas versionadas por separado en `schema/ddl/views/<view>.sql`;
4. manifest o inventario versionado de tablas, vistas e índices/fks;
5. tests de paridad:
   - local contra artefactos versionados;
   - MySQL CI contra `information_schema`;
6. un comando o script explícito para “registrar migraciones en prod sin DDL”;
7. documentación de rollback y de límites del baseline.

## Flujo principal

1. `flow release promote` resuelve el provider `github-actions`.
2. El provider dispara `promotion-pr.yml` en el repo derivado.
3. `promotion-pr.yml` crea o reutiliza un PR de promoción y registra `run_migrations`.
4. `promotion-pr-ci.yml` ejecuta `PR Promotion CI / release-quality-gates`.
5. Al mergearse el PR, `deploy-on-pr-merge.yml` ejecuta guardrails, deploy, release marker y healthcheck.
6. `flow release verify` consume la evidencia del entorno promovido.

## Slice Breakdown

```yaml
- name: provider-and-workflow-templates
  repo: sdd-workspace-boilerplate
  targets:
    - ../../scripts/providers/release/github_actions.sh
    - ../../templates/github-workflows/promotion-pr.yml
    - ../../templates/github-workflows/deploy-on-pr-merge.yml
    - ../../workspace.providers.json
    - ../../workspace.config.json
  hot_area: release/pr-promotion
  depends_on: []
- name: promotion-pr-ci-and-runbook
  repo: sdd-workspace-boilerplate
  targets:
    - ../../templates/github-workflows/promotion-pr-ci.yml
    - ../../docs/softos-pr-promotion-runbook.md
  hot_area: release/pr-promotion-ci
  depends_on:
    - provider-and-workflow-templates
- name: docs-and-schema-sync-contract
  repo: sdd-workspace-boilerplate
  targets:
    - ../../specs/features/softos-pr-promotion-deploy.spec.md
  hot_area: docs/pr-promotion
  depends_on:
    - promotion-pr-ci-and-runbook
```

## Criterios de aceptación

- existe `templates/github-workflows/promotion-pr.yml` con inputs `environment`, `source_ref`, `version`, `requested_by` y `run_migrations`;
- el template rechaza `staging <- main` y obliga `production` desde `staging`;
- existe `templates/github-workflows/deploy-on-pr-merge.yml` con guardrails, release marker y healthcheck;
- `scripts/providers/release/github_actions.sh` soporta `FLOW_DEPLOY_GITHUB_REPO`, `FLOW_DEPLOY_GITHUB_REF`, `FLOW_DEPLOY_SOURCE_REF` y `FLOW_DEPLOY_RUN_MIGRATIONS`;
- `release promote` y el provider `github-actions` aceptan `SOFTOS_GITHUB_TOKEN` como fuente de auth para `gh`;
- existe el runbook `docs/softos-pr-promotion-runbook.md`;
- `workspace.providers.json` y `workspace.config.json` incluyen un ejemplo versionado del patrón con `main` terminal;
- la spec documenta el contrato estándar de schema-sync por tabla.

## Test plan

- [@test] ../../scripts/providers/release/github_actions.sh
- validar sintaxis shell de `github_actions.sh`;
- validar sintaxis YAML de los templates;
- correr `flow ci spec` sobre esta spec.

## Rollout

1. publicar provider/template/runbook en SoftOS;
2. adoptar el patrón en derivados;
3. usar el contrato estándar en nuevas specs de schema-sync.

## Rollback

- revertir provider/templates/runbook a la versión previa;
- los derivados pueden seguir usando implementaciones propias si no adoptaron todavía el patrón reusable.
