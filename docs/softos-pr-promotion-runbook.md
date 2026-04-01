# SoftOS PR Promotion & Deploy Runbook

Usa este patrón cuando un repo de implementación promueve cambios por Pull Request entre ramas de entorno
(`main -> staging`, `staging -> production`, u otra política equivalente) y SoftOS debe disparar la promoción
desde `flow release promote` usando el provider `github-actions`.

## 1) Contrato en `workspace.config.json`

Declara el repo con provider de deploy por entorno y variables del workflow hijo:

```json
{
  "repos": {
    "legacy-api": {
      "deploy": {
        "provider": "github-actions",
        "providers_by_env": {
          "staging": "github-actions",
          "production": "github-actions"
        },
        "env": {
          "FLOW_DEPLOY_GITHUB_REPO": "acme/legacy-api",
          "FLOW_DEPLOY_GITHUB_WORKFLOW": "promotion-pr.yml",
          "FLOW_DEPLOY_GITHUB_REF": "main"
        },
        "env_by_env": {
          "production": {
            "FLOW_DEPLOY_SOURCE_REF": "staging"
          }
        }
      }
    }
  }
}
```

## 2) Provider reusable

SoftOS ya expone `scripts/providers/release/github_actions.sh` como provider reusable para `release promote`.

Inputs soportados:

- `FLOW_DEPLOY_GITHUB_REPO`: `owner/repo` destino.
- `FLOW_DEPLOY_GITHUB_WORKFLOW`: workflow a disparar; típico `promotion-pr.yml`.
- `FLOW_DEPLOY_GITHUB_REF`: rama/ref donde vive el workflow; por defecto `main`.
- `FLOW_DEPLOY_SOURCE_REF`: rama fuente a promover.
- `FLOW_DEPLOY_REQUESTED_BY`: operador que pide la promoción.
- `FLOW_DEPLOY_RUN_MIGRATIONS`: si se envía, pasa el flag `run_migrations` al workflow de promoción.

`flow release promote --env <env>` traduce `version` y `environment` al workflow hijo automáticamente.

## 3) Workflow hijo: Promotion PR

Copia y adapta [`templates/github-workflows/promotion-pr.yml`](/Users/john/Projects/Personal/softos-sdd-orchestrator/templates/github-workflows/promotion-pr.yml).

Reglas:

- usar solo `workflow_dispatch`
- no dispararlo con `push` ni `pull_request`
- crear o reusar el PR de promoción
- registrar `environment`, `source_ref`, `version`, `requested_by` y `run_migrations`

## 4) Workflow hijo: Deploy on PR merge

Copia y adapta [`templates/github-workflows/deploy-on-pr-merge.yml`](/Users/john/Projects/Personal/softos-sdd-orchestrator/templates/github-workflows/deploy-on-pr-merge.yml).

Reglas:

- disparar solo en `pull_request.closed`
- exigir `merged == true`
- filtrar por rama destino de entorno
- verificar aprobaciones adicionales en producción
- ejecutar guardrails antes del deploy real
- emitir y verificar release marker
- correr healthcheck post deploy

## 5) Guardrails canónicos

Usa [`scripts/release/hosting_path_guardrails.sh`](/Users/john/Projects/Personal/softos-sdd-orchestrator/scripts/release/hosting_path_guardrails.sh) para validar:

- path absoluto
- prefijo base permitido
- suffix/path guard por entorno
- aislamiento de `.env`
- aislamiento de `storage`
- rechazo de symlinks para `.env` y `storage`

El script es intencionalmente genérico: parametriza staging/production con variables de entorno en vez de
quedar acoplado a GoDaddy.

## 6) PR CI crítico

Copia y adapta [`templates/github-workflows/promotion-pr-ci.yml`](/Users/john/Projects/Personal/softos-sdd-orchestrator/templates/github-workflows/promotion-pr-ci.yml).

Check recomendado para branch protection:

- `PR Promotion CI / release-quality-gates`

Gates mínimos:

- tests críticos del repo
- build o empaquetado release
- smoke/lint específicos del deploy
- dry-run o smoke de migraciones si aplica
- cualquier chequeo de migración o contrato sensible

## 7) Branch protection recomendado

Para ramas de entorno (`staging`, `main`, o equivalentes):

- exigir PR, no pushes directos
- exigir `PR Promotion CI / release-quality-gates`
- exigir al menos un reviewer para producción
- restringir bypass de branch protection
- exigir checks verdes antes de merge en `staging` y `main`

## 8) Flujo operativo

1. `python3 ./flow release cut --version <v> --spec <slug>`
2. `python3 ./flow release promote --version <v> --env staging`
3. SoftOS dispara el workflow hijo `promotion-pr.yml`
4. El PR de promoción corre `promotion-pr-ci.yml`
5. Al mergear, `deploy-on-pr-merge.yml` ejecuta deploy + verify
6. `python3 ./flow release verify --version <v> --env staging --json`

Para `production`, el patrón es el mismo, pero con reviewer adicional y guardrails más estrictos.

## 9) Rollback

Rollback mínimo recomendado:

1. identificar el último release marker sano;
2. restaurar el artefacto o ref previo;
3. revalidar `.env`/`storage` isolation;
4. correr healthcheck;
5. ejecutar `python3 ./flow release verify --version <v> --env <env> --json` con evidencia del rollback.
