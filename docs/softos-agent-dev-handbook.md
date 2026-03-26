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

Valida contrato de specs: frontmatter, estado `approved`, `depends_on`, `[@test]` y consistencia estructural.

## `flow ci repo`

Valida por repo de implementación (instalación/lint/test/build según runtime).

## `flow ci integration --profile smoke`

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
```

Notas:

- `release promote` ejecuta verificación post-release por defecto.
- `--require-pipelines` fuerza que checks de pipeline estén disponibles y pasando.
- `--skip-verify` omite verificación automática (en `production` no marca la feature como `released`).

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
3. Ejecutar gates (`spec review` / `spec approve`) antes de implementación.
4. Ejecutar `ci spec`, luego `ci repo`/`ci integration`.
5. No cerrar ciclo sin evidencia de `release verify`.

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
- `specs/000-foundation/spec-as-source-operating-model.spec.md`
- `specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md`

