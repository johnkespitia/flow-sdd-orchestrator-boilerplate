---
name: Spec-Driven Delivery Bootstrap
description: Extender el control plane del workspace para gobernar CI, releases y cambios de infraestructura desde specs del root
status: approved
owner: platform
depends_on:
  - ../../specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
targets:
  - ../../AGENTS.md
  - ../../CURSOR.md
  - ../../OPENCODE.md
  - ../../flow
  - ../../flowctl/**
  - ../../Makefile
  - ../../README.md
  - ../../workspace.skills.json
  - ../../workspace.config.json
  - ../../workspace.providers.json
  - ../../runtimes/**
  - ../../.agents/skills/**
  - ../../.cursor/**
  - ../../.github/**
  - ../../docs/spec-driven-sdlc-map.md
  - ../../docs/spec-driven-orchestration.md
  - ../../docs/sdd-implementation-guide.md
  - ../../docs/softos-full-workflow.md
  - ../../docs/process-and-integrations-runbook.md
  - ../../docs/softos-pr-promotion-runbook.md
  - ../../specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - ../../specs/features/spec-driven-delivery-bootstrap.spec.md
  - ../../scripts/release/**
  - ../../scripts/providers/release/**
  - ../../scripts/infra/**
  - ../../scripts/preflight_env.sh
  - ../../templates/github-workflows/**
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
- manifiesto versionado de skills del workspace (`workspace.skills.json`)
- playbooks y archivos de compatibilidad para agentes (`.agents/skills/**`, `AGENTS.md`, `CURSOR.md`, `OPENCODE.md`, `.cursor/**`)
- entrypoints canónicos para ejecutar toolchains del workspace desde el devcontainer
- preflight de entorno agnóstico de runtime para validar readiness antes del primer spec

### Excluye

- despliegues reales a cloud providers
- integración con secretos o plataformas externas
- runners específicos de Terraform/Helm más allá del contrato de hooks

## Criterios de aceptación

- `python3 ./flow ci spec --all` valida el contrato de specs
- `python3 ./flow release cut --version <v> --spec spec-driven-delivery-bootstrap` genera un manifest versionado
- `python3 ./flow release promote --version <v> --env preview` registra una promoción usando el hook por defecto
- `python3 ./flow release promote --version <v> --env <env>` puede resolver automaticamente el provider de deploy desde `workspace.config.json` (`repos.<repo>.deploy`) sin `--provider`
- cuando un release incluye repos con providers de deploy distintos, `python3 ./flow release promote --version <v> --env <env> --deploy-repo <repo>` permite resolver la ambiguedad de forma explicita
- existe un provider de bridge para legado FTP (`ftp-bridge`) en `workspace.providers.json` para delegar deploy externo sin bypass del control plane
- existe un provider reusable `github-actions` capaz de disparar promotion PR workflows con `environment`, `version`, `source_ref` y `requested_by`
- `python3 ./flow infra plan spec-driven-delivery-bootstrap --env preview` genera un plan registrable solo para specs aprobadas
- `python3 ./flow infra apply spec-driven-delivery-bootstrap --env preview` ejecuta el hook por defecto y deja evidencia
- `python3 ./flow add-project <repo> --runtime <runtime>` persiste la configuracion CI derivada del runtime y permite overrides por step en el alta
- `python3 ./flow spec approve <spec> --approver <id>` requiere una review previa lista para aprobar
- `python3 ./flow spec create <slug> --runtime <pack> --service <pack> --capability <cap>` genera frontmatter declarativo con `schema_version: 2`
- `python3 ./flow spec review <spec>` y `python3 ./flow ci spec <spec>` fallan si `depends_on`, runtimes, servicios o capabilities declarados no existen o no estan listos
- `python3 ./flow workspace exec -- <cmd>` ejecuta el comando localmente cuando ya corre dentro del devcontainer y delega al servicio `workspace` cuando se invoca desde host
- `python3 ./flow repo exec <repo> -- <cmd>` ejecuta el comando en el `compose_service` del repo cuando existe, o localmente en el cwd del repo si ya corre dentro del devcontainer
- `python3 ./flow repo exec <repo> --workdir <path> -- <cmd>` permite fijar explícitamente el worktree o subpath materializado para evitar mezclar artefactos, autoloaders, módulos o cachés del checkout base con la slice bajo verificación
- `python3 ./flow worktree list --json` inventaría worktrees bajo `.worktrees/` y clasifica cuáles siguen activas, cuáles están cerradas y cuáles son huérfanas
- `python3 ./flow worktree clean --stale --json` elimina de forma segura worktrees huérfanas o cerradas sin cambios pendientes y ejecuta `git worktree prune`
- `python3 ./flow worktree clean --feature <slug> --dry-run --json` permite revisar el cleanup de una feature antes de mutar git
- `scripts/workspace_exec.sh <cmd>` y `make workspace ARGS='<cmd>'` reutilizan el mismo entrypoint canónico del workspace para evitar ejecutar toolchains del proyecto directamente en el host
- la imagen `workspace` incluye `pytest` para que las regresiones Python del control plane puedan validarse dentro del devcontainer sin depender del host
- los handoffs y reportes de ejecución deben sugerir `flow repo exec <repo> -- <cmd>` para comandos del runtime del repo, evitando inducir a subagentes a correr PHPUnit, Composer, pnpm, pytest o Go test en `workspace`
- esos handoffs deben apuntar al `--workdir` del worktree de la slice cuando el flujo se ejecuta sobre materialización aislada
- la higiene de worktrees debe tratar `.worktrees/**` como artefactos operativos temporales y preservar solo worktrees activas, worktrees con cambios no integrados o worktrees explicitamente retenidas para la siguiente ola inmediata
- las specs y slices de enforcement, governance, minimal-change o verification-only deben declarar explícitamente si una nueva superficie es `required`, `optional` o `forbidden`
- cuando una slice no exige expansión funcional, la spec debe declarar `minimum_valid_completion`, `validated_noop_allowed` y `acceptable_evidence`
- `flow plan`, `workflow next-step` y `workflow execute-feature --start-slices` deben preservar ese contrato de cierre mínimo en el plan y en los handoffs para que el ejecutor pueda cerrar con enforcement/tests/verificación sin reabrir alcance
- `workspace.skills.json` puede registrar skills locales versionados con `provider=tessl`, `kind=skill`, `source` relativo al workspace y `sync=false`
- los runtime packs en `runtimes/*.runtime.json` pueden exponer esos playbooks locales via `agent_skill_refs`, y `python3 ./flow skills context --repo <repo> --json` resuelve los paths efectivos en `.agents/skills/**` o `.tessl/tiles/**`
- `python3 ./flow stack design --spec <slug>`, `stack plan --spec <slug>` y `stack apply --spec <slug>` derivan `workspace.stack.json` desde una spec aprobada con `stack_projects`, `stack_services` y `stack_capabilities`
- los runtime packs pueden declarar `bindings` por runtime de servicio para resolver `environment` y `depends_on` sin modificar el core
- las foundation specs generadas por capabilities nacen en `draft`, no en `approved`
- `python3 ./flow release cut --spec <slug>` falla si el plan no existe o si alguna slice planeada no paso verificacion
- `scripts/preflight_env.sh --build` valida salud base del workspace y falla si hay servicios sin readiness operativo
- el boilerplate publica templates reusables de `promotion-pr`, `deploy-on-pr-merge` y `promotion-pr-ci`, mas un guardrail canónico de path/aislamiento para despliegues promotion-by-PR

## Contratos derivados

## Gobernanza de slices de cumplimiento

Cuando una slice preserve contrato o solo endurezca enforcement, la spec debe declarar el cierre mínimo válido y no dejarlo a interpretación del ejecutor.

### Reglas

- `slice_mode` puede ser `implementation-heavy`, `refactor`, `governance`, `enforcement`, `minimal-change` o `verification-only`
- `surface_policy` debe declarar si la superficie nueva es `required`, `optional` o `forbidden`
- si `slice_mode` es `governance`, `enforcement`, `minimal-change` o `verification-only`, o si `surface_policy != required`, la slice debe declarar:
  - `minimum_valid_completion`
  - `validated_noop_allowed`
  - `acceptable_evidence`
- una slice `verification-only` no puede exigir superficie nueva
- el handoff resultante debe instruir al ejecutor a cerrar con el mínimo entregable y la evidencia declarada cuando no exista expansión funcional obligatoria

```json contract
{
  "name": "Release Manifest Envelope",
  "type": "json-schema",
  "repo": "sdd-workspace-boilerplate",
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

```json contract
{
  "name": "Release Promote Deploy Routing",
  "type": "json-schema",
  "repo": "sdd-workspace-boilerplate",
  "match": [
    "flowctl/release.py",
    "flowctl/parser.py",
    "workspace.providers.json",
    "scripts/providers/release/ftp_bridge.sh",
    "scripts/providers/release/github_actions.sh",
    "scripts/release/hosting_path_guardrails.sh",
    "templates/github-workflows/promotion-pr.yml",
    "templates/github-workflows/deploy-on-pr-merge.yml",
    "templates/github-workflows/promotion-pr-ci.yml"
  ],
  "contains": [
    "_resolve_release_provider_from_workspace",
    "--deploy-repo",
    "ftp-bridge",
    "FLOW_DEPLOY_GITHUB_REPO",
    "FLOW_DEPLOY_SOURCE_REF",
    "requested_by",
    "hosting_path_guardrails.sh"
  ],
  "schema": {
    "type": "object"
  }
}
```
