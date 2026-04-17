# SoftOS Agent & Dev Handbook

Esta guía concentra el proceso operativo completo para que cualquier agente o developer pueda usar este SoftOS de punta a punta sin adivinar pasos.

## 1) Modelo mental

SoftOS en este workspace tiene 3 capas:

- `specs/**`: fuente de verdad funcional/arquitectónica.
- `flow` + `flowctl/**`: kernel operativo del SDLC y del stack.
- `gateway/**`: capa HTTP para intents/webhooks (Jira/GitHub/Slack) que termina ejecutando `flow`.

Regla: no ejecutar procesos “por fuera” del control plane si existe comando `flow` equivalente.

## 2) Onboarding rápido (nuevo workspace)

1. Crear workspace desde boilerplate o bootstrap.
2. Abrir en devcontainer.
3. Ejecutar bootstrap base:

```bash
python3 ./flow init
python3 ./flow doctor
python3 ./flow workflow doctor --json
python3 ./flow providers doctor
python3 ./flow secrets doctor
python3 ./flow submodule doctor --json
```

`flow init` también configura `core.hooksPath=scripts/git-hooks` para activar hooks versionados (`pre-commit`, `pre-push`).

## 3) Flujo estándar de feature (SDLC)

### 3.1 Intake y diseño

```bash
python3 ./flow workflow intake <slug> --title "<Title>" --repo root --runtime <runtime> --service <service> --json
python3 ./flow workflow next-step <slug> --json
```

### 3.2 Gates de spec

```bash
python3 ./flow spec review <slug>
python3 ./flow spec approve <slug> --approver <id>
```

### 3.3 Ejecución

```bash
python3 ./flow workflow execute-feature <slug> --start-slices --json
python3 ./flow slice verify <slug> <slice>
python3 ./flow status <slug> --json
```

### 3.4 Gobernanza/validación

```bash
python3 ./flow ci spec --all
python3 ./flow drift check --all --json
python3 ./flow contract verify --all --json
```

## 4) CI operativo (qué valida cada capa)

## `flow ci spec`

Valida contrato de specs: frontmatter, estado `approved|released`, `depends_on`, `[@test]` y consistencia estructural.
Cuando una spec declare `## Verification Matrix`, `flow ci spec` valida tambien la estructura de esos perfiles transversales.

## `flow ci repo`

Valida por repo de implementación (instalación/lint/test/build según runtime).

Si un repo trae su pipeline propio y quieres que solo lo ejecute el root CI de SoftOS, declara en
`workspace.config.json`:

```json
"ci": {
  "mode": "workflow-dispatch",
  "workflow": "repo-ci.yml",
  "trigger_mode": "workflow_dispatch_only"
}
```

Notas:

- el workflow hijo no debe tener `push`/`pull_request`; solo `workflow_dispatch`
- `root-ci.yml` lo despacha desde SoftOS y espera su resultado
- si el repo no declara `ci.mode=workflow-dispatch`, cae al `flow ci repo <repo>` genérico

## `flow ci integration --profile smoke`

Las pruebas transversales declaradas en `## Verification Matrix` deben usar comandos ejecutables desde el root del workspace, por ejemplo `scripts/workspace_exec.sh ...`, `python3 ./flow ci integration ...` o `python3 ./flow repo exec ...`.

Valida salud del stack y smoke por servicio.

Incluye hardening:

- retries/backoff para `stack up` cuando `--auto-up`.
- retries/backoff por smoke command de servicio.
- categorización de checks (`infra` vs `app`).
- espera de `healthy` cuando el servicio expone healthcheck Compose.
- preflight contracts por runtime (advisory por defecto, estricto en perfil `smoke:ci-clean`).
- diagnóstico de fallos con tail del último intento.

Variables de tuning:

- `FLOW_CI_STACK_UP_ATTEMPTS`
- `FLOW_CI_STACK_UP_BACKOFF_SECONDS`
- `FLOW_CI_SMOKE_ATTEMPTS`
- `FLOW_CI_SMOKE_BACKOFF_SECONDS`
- `FLOW_CI_HEALTH_TIMEOUT_SECONDS`
- `FLOW_CI_HEALTH_POLL_SECONDS`

## 5) Releases e infraestructura

### 5.1 Release

```bash
python3 ./flow release cut --version <v> --spec <slug>
python3 ./flow release promote --version <v> --env <preview|staging|production>
python3 ./flow release verify --version <v> --env <preview|staging|production> --json
python3 ./flow release status --version <v> --json
python3 ./flow release publish --bump <auto|patch|minor|major> [--skip-github] [--dry-run] --json
```

Notas:

- `release promote` ejecuta verificación post-release por defecto.
- `--require-pipelines` fuerza que checks de pipeline estén disponibles y pasando.
- `--skip-verify` omite verificación automática (en `production` no marca la feature como `released`).
- `release publish` es la capa de release OSS del repo: actualiza `CHANGELOG.md`, crea commit/tag semver y opcionalmente publica GitHub Release.
- `release publish --bump auto` infiere el semver desde commits convencionales (`feat` -> minor, `fix` -> patch, `!`/`BREAKING CHANGE` -> major).
- `github-actions` puede despachar promotion PR reusables en repos derivados con
  `FLOW_DEPLOY_GITHUB_WORKFLOW`, `FLOW_DEPLOY_GITHUB_REPO`, `FLOW_DEPLOY_GITHUB_REF`,
  `FLOW_DEPLOY_SOURCE_REF` y `FLOW_DEPLOY_REQUESTED_BY`.

Artefactos:

- Manifest: `releases/manifests/<version>.json`
- Promoción: `releases/promotions/<version>-<env>.json`
- Verificación: `releases/promotions/<version>-<env>-verification.json`

### 5.2 Infra

```bash
python3 ./flow infra plan <slug> --env <env> --json
python3 ./flow infra apply <slug> --env <env> --json
python3 ./flow infra status <slug> --json
```

## 6) Submódulos y guardrails

Comandos clave:

```bash
python3 ./flow submodule doctor --json
python3 ./flow submodule sync --json
./scripts/ci/normalize_gitmodules.sh --check-only
```

Protecciones activas:

- `pre-push` bloquea gitlinks no fetchables en remoto.
- `normalize_gitmodules.sh` valida gitlinks antes de hidratar submódulos.

## 7) Uso por agentes

Secuencia recomendada para agentes:

1. `flow doctor` + `flow workflow doctor`.
2. Resolver spec objetivo y foundations (`specs/000-foundation/**`).
3. Ejecutar gates (`spec review` / `spec approve` / `spec approval-status --json`) antes de planear.
4. Ejecutar `flow plan`, luego `plan-approve` y `plan-approval-status --json` antes de iniciar slices.
5. Ejecutar `flow policy check <spec> --stage slice-start --json` antes de comandos sensibles.
6. Para ejecucion autonoma con aprobaciones humanas, usar `flow workflow run <spec> --human-gated --json`.
7. Ejecutar `flow evidence status <spec> --json` y `flow evidence bundle <spec> --json` para consolidar evidencia.
8. Ejecutar `flow agent handoff <spec> --json` cuando otro agente deba retomar sin contexto del chat.
9. Ejecutar `ci spec`, luego `ci repo`/`ci integration`.
10. No cerrar ciclo sin evidencia de `release verify`.

### 7.0 Tooling externo

BMAD, Tessl, Engram y skills externos se actualizan por capas: binarios del devcontainer,
assets versionados del workspace y estado operativo local. El manual operativo vive en
[`docs/external-tooling-updates.md`](external-tooling-updates.md).

Regla practica:

- usar `latest` solo para workspaces de desarrollo reconstruidos conscientemente
- pinnear versiones con build args para staging, produccion, demos o releases reproducibles
- revisar cualquier diff en `_bmad/**`, `.tessl/**` o `.agents/skills/**` como cambio versionado normal
- respaldar Engram con `flow memory backup` antes de upgrades de runtime

### 7.1 Memoria consultiva de agentes

SoftOS puede usar Engram como memoria opcional para agentes. Esta memoria sirve para recuperar
aprendizajes reutilizables, gotchas y outcomes entre sesiones, pero no es fuente de verdad.

Instalacion y aislamiento:

- Engram se instala automaticamente al reconstruir el devcontainer `workspace`.
- La memoria queda en `/workspace/.flow/memory/engram` dentro del contenedor.
- `.flow/memory/**` queda fuera de git para evitar contaminar el repo con memoria local.
- `ENGRAM_PROJECT` identifica el workspace; por defecto este repo usa `softos-sdd-orchestrator`.
- Los workspaces creados con `scripts/bootstrap_workspace.py` reciben `ENGRAM_PROJECT` y
  `memory.agent.project` derivados de `--root-repo`; no heredan la DB local del boilerplate.

Playbook:

- `.agents/skills/softos-agent-memory-playbook/SKILL.md`

Reglas:

- consultar memoria al iniciar tareas donde haya historial útil de spec, repo, release o gateway
- guardar solo aprendizajes reutilizables al cerrar tareas verificadas
- no guardar secretos, tokens, PII ni logs brutos
- no usar memoria para saltar `spec review`, `ci`, `release` ni evidencia declarada
- si Engram no está instalado, continuar el SDLC normalmente

Comandos operativos:

```bash
python3 ./flow memory doctor --json
python3 ./flow memory stats --json
python3 ./flow memory search "softos gateway release gotcha" --json
python3 ./flow memory export --json
python3 ./flow memory backup --json
python3 ./flow memory import .flow/memory/backups/<file>.json --json
python3 ./flow memory import .flow/memory/backups/<file>.json --confirm --json
python3 ./flow memory prune --query smoke --keep-latest 200 --json
python3 ./flow memory save "SoftOS handoff outcome" --body "TYPE: outcome
Project: softos-sdd-orchestrator
Area: <spec-or-hot-area>
What: <reusable fact>
Why: <impact>
Where: <source files/specs/reports>
Evidence: <commands run>
Learned: <instruction for future agents>" --json
python3 ./flow memory smoke --json
python3 ./flow memory smoke --save --json
python3 ./flow plan <spec> --memory-recall
python3 ./flow release publish --version v0.9.x --memory-save-outcome
```

Resultado esperado:

- `doctor` retorna cero aunque Engram falte y muestra `available=false`
- `search` es el camino principal para recall de memorias existentes
- `search --json` expone `items[]` parseado y conserva `raw_stdout`
- `export` usa `engram export` nativo para crear respaldo JSON bajo `.flow/memory/exports/`
- `backup` crea un export timestamped bajo `.flow/memory/backups/`
- `import` es dry-run por defecto; solo ejecuta `engram import` con `--confirm`
- `prune` es un reporte advisory no destructivo; Engram no expone delete granular seguro
- `save` requiere input explicito y no debe usarse con secretos ni logs brutos
- `smoke` valida `engram version`, `engram stats`, `engram context <project>` y `engram search <project>`
- `smoke --save` persiste una memoria reusable de prueba en la DB local del workspace
- ningún comando de `flow` depende de esa memoria para pasar
- `.github/workflows/memory-smoke.yml` ofrece `Memory Smoke` manual en devcontainer; no corre en `push` ni `pull_request`
- `plan --memory-recall` y `release publish --memory-save-outcome` son gates explicitos; la config
  `memory.execution` los deja apagados por defecto para evitar guardar basura

MCP opcional:

- `.cursor/mcp.json` activa Engram para Cursor a nivel de proyecto cuando Cursor corre dentro del devcontainer.
- `opencode.json` activa Engram para OpenCode a nivel de proyecto.
- `.mcp.example.json` conserva una configuracion generica opt-in para clientes compatibles con `mcpServers`.
- Codex usa configuracion de usuario; activar con `scripts/install_codex_engram_mcp.sh`.
- Todas las variantes usan `engram mcp` y `ENGRAM_DATA_DIR=/workspace/.flow/memory/engram`.
- Verificar primero:

```bash
python3 ./flow memory doctor --json
engram mcp --help
scripts/install_codex_engram_mcp.sh
```

Checklist mínimo antes de declarar “done”:

- Spec en `approved`.
- Slices verificadas.
- `ci spec` verde.
- `ci integration` verde (o findings justificados).
- `release promote` + `release verify` para entorno objetivo.

## 8) Troubleshooting rápido

Si falla `ci integration`:

1. Revisar categoría del check (`infra` vs `app`).
2. Abrir markdown report en `.flow/reports/ci/integration-<profile>.md`.
3. Usar `output_tail` del smoke fallido para diagnóstico.
4. Confirmar healthchecks y estado Compose:

```bash
python3 ./flow stack ps
python3 ./flow stack logs
```

Si falla `release verify`:

1. Revisar `releases/promotions/<version>-<env>-verification.json`.
2. Validar SHA remoto de repos del manifest.
3. Si `--require-pipelines`, confirmar check-runs del commit.

Si falla submódulo en CI:

1. Confirmar que el SHA del submódulo exista en remoto.
2. Ejecutar localmente `./scripts/ci/normalize_gitmodules.sh --check-only`.

## 9) Documentos de referencia

- `docs/softos-full-workflow.md`
- `docs/spec-driven-orchestration.md`
- `docs/spec-driven-sdlc-map.md`
- `docs/process-and-integrations-runbook.md`
- `docs/softos-pr-promotion-runbook.md`
- `specs/000-foundation/spec-as-source-operating-model.spec.md`
- `specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md`
