# SoftOS SDD Orchestrator Boilerplate

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](#)
[![CI](https://img.shields.io/badge/ci-root--ci-success-brightgreen.svg)](#)
[![Gateway](https://img.shields.io/badge/gateway-fastapi-009688.svg)](#)

Plantilla base para levantar un workspace **Spec-Driven Delivery (SDD)** con `flow` + Tessl + BMAD.

## TL;DR

- `specs/**` como fuente de verdad.
- `flow` como control plane del SDLC y del stack.
- `gateway/` como ingress HTTP central para webhooks/intents.
- Bootstrap en dos perfiles: `master` (control plane completo) y `slave` (runner conectado a gateway remoto).

## Quick Navigation

- [Qué trae](#qué-trae)
- [Uso recomendado](#uso-recomendado)
- [Perfiles master/slave](#perfiles-de-bootstrap-master-y-slave)
- [Después de crear tu workspace](#después-de-crear-tu-workspace)
- [Gateway de Integraciones](#gateway-de-integraciones)
- [Contribuir](./CONTRIBUTING.md)
- [Seguridad](./SECURITY.md)
- [Código de conducta](./CODE_OF_CONDUCT.md)

Template repo para levantar un workspace de `Spec As Source` con:

- `specs/**` como fuente de verdad
- `flow` como control plane del SDLC y del stack
- Tessl como capa metodológica de SDD
- BMAD como runtime de orquestación por defecto encima de `flow`
- devcontainer reproducible para el equipo
- repos de implementación separados del root del workspace

No es un producto específico. Es una base reusable para crear workspaces agentic y spec-driven.

## Qué trae

- `flow`: CLI del workspace para `stack`, `tessl`, `skills`, `bmad`, `workflow`, `add-project`, `spec`, `plan`, `slice`, `ci`, `release`, `infra`, `submodule`, `secrets`, `drift`, `status`
- `workspace.config.json`: routing configurable de repos, targets y test runners
- `flowctl/`: módulos internos del control plane para el refactor incremental
- `workspace.skills.json`: capacidades del agente, separadas del scaffolding
- `workspace.runtimes.json`: catálogo versionado de runtime packs
- `workspace.capabilities.json`: catálogo versionado de capabilities como GraphQL
- `workspace.stack.json`: manifiesto declarativo del stack inferido o planeado
- `workspace.providers.json`: manifest versionado de providers de release e infraestructura
- `gateway/`: ingress FastAPI del SoftOS para Jira, Slack y GitHub
- `workspace.secrets.json`: manifest versionado de providers de secrets y archivos generados
- `.tessl/**`: tile local de SDD centrado en root
- `_bmad/`: instalación versionada del runtime BMAD del proyecto
- `.flow/**`: estado operativo local del SDLC
- `.devcontainer/**`: chasis reproducible con `workspace` y runtime packs listos para crecer
- `scripts/bootstrap_workspace.py`: scaffolder para generar un proyecto nuevo sin heredar Git

## Qué parte es boilerplate y qué parte es ejemplo

Reusable:

- `specs/**`
- `.tessl/**`
- `flow`
- `Makefile`
- `workspace.config.json`
- `scripts/bootstrap_workspace.py`
- `_bmad/`

Ejemplo reemplazable:

- topología del devcontainer
- runtime packs en `runtimes/*.runtime.json`
- comandos de instalación por defecto del `Makefile`

## Uso recomendado

### Opción 1: usar este repo como template

1. En GitHub usa `Use this template`
2. Crea tu nuevo repo
3. Clona el repo nuevo
4. Ajusta nombres del proyecto con `bootstrap_workspace.py` si todavía quieres renombrar el root

### Opción 2: generar un proyecto aislado desde este repo

Desde este boilerplate:

```bash
python3 scripts/bootstrap_workspace.py /ruta/al/nuevo-workspace \
  --project-name "Acme Platform" \
  --root-repo acme-dev-env \
  --git-init
```

Eso genera un workspace nuevo:

- con su propio `.git`
- con `workspace.config.json` ya ajustado
- con un chasis root-only limpio
- sin arrastrar estado operativo previo

### Perfiles de bootstrap: `master` y `slave`

`bootstrap_workspace.py` soporta perfiles para copiar solo lo necesario:

- `master`: instala control-plane completo (incluye `gateway/` y operación central).
- `slave`: instala runner de desarrollo (excluye `gateway/`) y configura conexión a gateway remoto.

Ejemplo `master`:

```bash
python3 scripts/bootstrap_workspace.py /ruta/master \
  --project-name "SoftOS Master" \
  --root-repo softos-master \
  --profile master
```

Ejemplo `slave`:

```bash
python3 scripts/bootstrap_workspace.py /ruta/slave \
  --project-name "SoftOS Dev Runner" \
  --root-repo softos-dev-runner \
  --profile slave \
  --gateway-url https://gateway.example.internal
```

Si en `slave` no pasas `--gateway-url`, el script la pide por prompt. Por defecto valida `GET /healthz`
del gateway remoto (puedes omitir con `--skip-gateway-check`).

En `slave`, además, persiste:

- `workspace.config.json` con `gateway.connection = {"mode":"remote","base_url":"..."}`
- `.env.gateway` con `SOFTOS_GATEWAY_URL` y placeholder de `SOFTOS_GATEWAY_API_TOKEN`

## Después de crear tu workspace

1. Abre el root en devcontainer
2. Ejecuta el primer arranque
3. Diseña o agrega los proyectos que realmente necesites con `flow stack design|plan|apply` o `flow add-project`
4. Ajusta [`workspace.config.json`](workspace.config.json) si tu routing requiere reglas adicionales
5. Si tu stack necesita otro runtime base, cambia los runtime packs o [`.devcontainer/docker-compose.yml`](.devcontainer/docker-compose.yml)
6. Ejecuta:

Nota:

- `devcontainer.json` añade mounts y variables para que `python3 ./flow stack ...` y
  `python3 ./flow doctor` funcionen tambien desde dentro del `workspace`
- si cambias `.devcontainer/**`, usa **Rebuild Container**; un `docker compose up` directo no aplica
  toda la capa extra que inyecta Cursor/VS Code
- en macOS, activa **VirtioFS**; el boilerplate ya usa volúmenes nombrados para `vendor/`,
  `node_modules/` y el store de `pnpm`

```bash
python3 ./flow init
python3 ./flow doctor
python3 ./flow stack doctor
python3 ./flow tessl -- --help
python3 ./flow skills doctor
python3 ./flow secrets doctor
python3 ./flow secrets scan --all --json
python3 ./flow providers doctor
python3 ./flow bmad -- status
python3 ./flow workflow doctor --json
python3 ./flow submodule doctor --json
python3 ./flow ci spec --all
python3 ./flow drift check --all --json
python3 ./flow contract verify --all --json
python3 ./flow spec generate-contracts spec-driven-delivery-bootstrap --json
python3 ./flow release --help
python3 ./flow infra --help
```

`flow init` materializa `.devcontainer/.env.generated` si falta, levanta el stack y deja visible la
URL de health del gateway. Si `8010` ya esta ocupado en tu host, puedes mover el puerto expuesto
sin editar el repo:

```bash
SOFTOS_GATEWAY_HOST_PORT=18010 python3 ./flow init --build
```

`flow init` tambien configura `core.hooksPath=scripts/git-hooks` en el repo local para activar los
hooks versionados (incluido `pre-push` para validar gitlinks de submodulos antes de subir cambios).

Desde tu shell host, una vez el servicio `workspace` este arriba, `flow tessl`, `flow bmad`,
`flow skills doctor`, `flow skills sync` y `flow ci repo` delegan automaticamente al devcontainer.
Para cualquier otro comando del toolchain del workspace, usa `python3 ./flow workspace exec -- ...`
o el wrapper `scripts/workspace_exec.sh ...` en vez de probar primero en el host.
Para comandos del runtime de un repo concreto, usa `python3 ./flow repo exec <repo> -- ...` para que se ejecuten en el contenedor del proyecto.

Si necesitas un tercer proyecto de implementación, puedes registrarlo desde el control plane:

```bash
python3 ./flow add-project api --runtime php --port 8000
python3 ./flow add-project web --runtime pnpm --port 5173
python3 ./flow add-project mobile --runtime pnpm --port 4173
```

Eso actualiza `workspace.config.json`, crea el directorio placeholder y, si el runtime lo soporta,
agrega el servicio al `docker-compose` del devcontainer junto con auxiliares del runtime. El
runtime `php`, por ejemplo, agrega `db` si todavía no existe.

Los runtime packs tambien pueden declarar CI minimo reproducible. `flow add-project` persiste esos
steps en `workspace.config.json` para que `flow ci repo` no dependa solo de deteccion heuristica.
Si hace falta, puedes overridearlos por proyecto con `--ci-install`, `--ci-lint`, `--ci-test`,
`--ci-build` o desactivar defaults con `--no-ci-step`.

Tambien puedes partir desde una intencion conversacional y dejar que el control plane diseñe el
stack inicial sobre el chasis limpio:

```bash
python3 ./flow stack design --prompt "quiero una api en golang que se conecte a postgresql y sea consumible usando graphql" --json
python3 ./flow stack plan --json
python3 ./flow stack apply --json
```

Ese flujo:

- escribe `workspace.stack.json`
- agrega servicios standalone como `postgres` o `mongo` sin crear repos falsos
- crea proyectos reales de implementacion con runtime packs como `go-api`
- genera foundation specs derivadas desde `workspace.capabilities.json`, por ejemplo GraphQL

Si ya tienes una spec aprobada, tambien puedes derivar el stack desde la spec misma:

```bash
python3 ./flow stack design --spec stack-from-spec --json
python3 ./flow stack plan --spec stack-from-spec --json
python3 ./flow stack apply --spec stack-from-spec --json
```

En ese modo la topologia debe venir declarada en el frontmatter con `stack_projects`,
`stack_services` y `stack_capabilities`.

Matiz operativo:

- `flow spec review` valida una spec en `draft`
- `flow stack design --spec` y `flow stack plan --spec` pueden previsualizar una spec `draft` si ya esta lista para aprobar
- `flow ci spec` y `flow stack apply --spec` siguen exigiendo `status: approved`

Campos estructurales soportados ahora:

- `stack_projects[*].name`, `runtime`, `path`, `port`
- `stack_projects[*].repo_code`, `compose_service`, `aliases`
- `stack_projects[*].service_bindings`, `capabilities`, `env`
- `stack_projects[*].default_targets`, `target_roots`, `use_existing_dir`
- `stack_services[*].name`, `runtime`, `env`, `ports`, `volumes`

`stack design --prompt` ya no materializa el stack. Solo redacta una spec draft con esos
campos explicitados para review. El manifest real se deriva despues con `--spec`.

## Gateway de Integraciones

El boilerplate ya incluye `gateway/` como ingress module del SoftOS. Reutiliza `python3 ./flow`
como kernel y expone adapters inbound para Jira, Slack y GitHub sin duplicar la logica del SDLC.

Superficie expuesta:

- `GET /healthz`
- `POST /v1/intents`
- `GET /v1/tasks/{task_id}`
- `POST /webhooks/slack/commands`
- `POST /webhooks/github`
- `POST /webhooks/jira`

Notas:

- el gateway es parte del core del boilerplate, pero no reemplaza `flow`
- la cola es secuencial y persiste en `gateway/data/tasks.db`
- el feedback usa `workspace.providers.json`
- si Slack, GitHub o Jira no tienen credenciales reales, el feedback cae en `local-log`
- el intake externo nuevo entra por `workflow.intake`, no por `spec.create`, para que BMAD y Tessl participen desde el inicio

Arranque basico:

```bash
python3 ./flow init
curl -fsSL "http://127.0.0.1:${SOFTOS_GATEWAY_HOST_PORT:-8010}/healthz"
```

Happy path nuevo para una iniciativa:

```bash
python3 ./flow workflow intake users-api --title "Users API" --repo root --runtime go-api --service postgres-service --json
python3 ./flow workflow next-step users-api --json
```

Las skills y tiles del workspace también se gobiernan desde el control plane:

```bash
python3 ./flow skills doctor
python3 ./flow skills list
python3 ./flow skills sync --dry-run
python3 ./flow skills add team-review --provider skills-sh --source your-org/agent-skills --arg=--copy
python3 ./flow skills add github-review --provider skills-sh --source your-org/agent-skills --require gh
python3 ./flow skills install demo/skill --provider tessl --runtime go-api
```

Los runtimes de `flow add-project` se resuelven desde `workspace.runtimes.json` y `runtimes/*.runtime.json`,
dejando `workspace.skills.json` reservado para capacidades del agente:

```bash
python3 ./flow add-project api --runtime php --port 8000
python3 ./flow add-project web --runtime pnpm --port 5173
python3 ./flow add-project legacy-api --path projects/legacy-api --runtime php \
  --submodule-url git@github.com:acme/legacy-api.git --submodule-branch main
```

Los runtime packs tambien pueden declarar `bindings` por runtime de servicio. Ese contrato define
como un proyecto se enlaza con servicios como `postgres-service` o `mongo-service`, incluyendo
`environment` y `depends_on`, sin tocar el core de `flow`.

Los providers de CD e infraestructura se gobiernan igual:

```bash
python3 ./flow providers doctor
python3 ./flow providers list
python3 ./flow release promote --version 2026.03.14-1 --env preview --provider local-hooks
python3 ./flow release verify --version 2026.03.14-1 --env preview --json
python3 ./flow infra plan spec-driven-delivery-bootstrap --env preview --provider local-hooks
```

Deploy transparente por repo:

- `flow release promote` ahora puede resolver provider automaticamente desde `workspace.config.json`
  usando `repos.<repo>.deploy`.
- `flow release promote` ejecuta verificacion post-release por defecto (repos + pipelines cuando aplica).
- Usa `--require-pipelines` para exigir confirmacion de checks de pipeline en cada repo del release.
- Usa `--skip-verify` para omitir la verificacion automatica (en `production` no marca `released`).
- `flow release verify` permite reintentar/verificar manualmente y deja evidencia en
  `releases/promotions/<version>-<env>-verification.json`.
- Si un release toca varios repos con providers distintos, usa `--deploy-repo <repo>` o `--provider`.
- El provider `github-actions` tambien puede disparar un workflow reusable de PR-promotion con
  `FLOW_DEPLOY_GITHUB_WORKFLOW`, `FLOW_DEPLOY_GITHUB_REPO`, `FLOW_DEPLOY_GITHUB_REF`,
  `FLOW_DEPLOY_SOURCE_REF` y `FLOW_DEPLOY_REQUESTED_BY`.

Contrato recomendado en `workspace.config.json` por repo:

```json
{
  "repos": {
    "legacy-api": {
      "deploy": {
        "provider": "ftp-bridge",
        "providers_by_env": {
          "preview": "github-actions",
          "production": "ftp-bridge"
        },
        "env": {
          "FLOW_DEPLOY_GITHUB_REPO": "acme/legacy-api",
          "FLOW_DEPLOY_GITHUB_WORKFLOW": "deploy.yml"
        },
        "env_by_env": {
          "production": {
            "FLOW_DEPLOY_GITHUB_REF": "main"
          }
        }
      }
    }
  }
}
```

`ftp-bridge` delega el deploy legacy a un workflow de GitHub del repo de implementacion (`gh workflow run`),
manteniendo el gate y la auditoria dentro de SoftOS.

Si tu estrategia de deploy es promotion-by-PR, usa las plantillas canónicas:

- `templates/github-workflows/promotion-pr.yml`
- `templates/github-workflows/deploy-on-pr-merge.yml`
- `templates/github-workflows/promotion-pr-ci.yml`
- `scripts/release/hosting_path_guardrails.sh`
- `docs/softos-pr-promotion-runbook.md`

Si exportas `SOFTOS_SLACK_WEBHOOK_URL`, los hooks locales publican un resumen final del delivery:
fallo en `release promote`, `infra plan` o `infra apply`, y `change ready` cuando `infra apply`
termina en verde.

Los secrets y guardrails de repos también entran por el control plane:

```bash
python3 ./flow secrets list
python3 ./flow secrets scan --all --json
python3 ./flow secrets sync --dry-run
python3 ./flow submodule doctor --json
python3 ./flow drift check --all --json
python3 ./flow contract verify --all --json
make hooks-install
```

`flow drift check` valida que `[@test]` apunte a tests ejecutables por el `test_runner` del repo.
`flow contract verify` usa los contratos generados en `contracts/generated/**` para detectar drift
estructural entre contrato e implementacion antes de llegar a integración.

Guardrail adicional (hooks + CI):

- `scripts/guardrails/check_boilerplate_protected_paths.sh` bloquea cambios en archivos core del
  boilerplate (lista en `scripts/guardrails/boilerplate_protected_paths.txt`) para evitar ediciones
  accidentales por agentes en workspaces derivados.
- Override intencional:
  - `ALLOW_BOILERPLATE_CORE_CHANGES=1` para bypass puntual.
  - `ENFORCE_BOILERPLATE_GUARDRAILS=1` para forzar también en el repo fuente del boilerplate.

## CI y submódulos privados (GitHub Actions)

Cuando el workspace usa submódulos privados en GitHub, el `GITHUB_TOKEN` por defecto del workflow
puede no tener acceso a repos privados adicionales (aunque estén bajo el mismo usuario/organización).

Por eso `root-ci` usa este enfoque:

1. `actions/checkout@v4` con `submodules: false`.
2. Paso `Normalize and hydrate submodules` con `./scripts/ci/normalize_gitmodules.sh`.
3. Autenticación del checkout con:

```yaml
token: ${{ secrets.GH_PAT || github.token }}
```

Si existe `GH_PAT`, se usa ese token; si no, el workflow cae al `github.token`.

Adicionalmente, `root-ci` separa `Repo CI` en una matrix por repo/runtime:

- `discover-repo-ci-matrix` detecta repos de implementación y runtime desde `workspace.config.json`.
- `repo-ci` ejecuta `python3 ./flow ci repo <repo>` en paralelo por repo.
- Cada fila instala toolchains condicionales (solo los necesarios según runtime/CI commands), por
  ejemplo `go`, `node`/`pnpm` o `php`/`composer`.
- La ejecución fuerza modo nativo en runner con:

```bash
FLOW_SKIP_COMPOSE_WRAP=1
```

Eso evita depender de `docker compose exec` cuando el servicio `workspace` no está levantado en
GitHub Actions.

### Qué hace `scripts/ci/normalize_gitmodules.sh`

- Si no existe `.gitmodules`, hace no-op.
- Valida que cada gitlink del root apunte a un commit fetchable en el remoto del submódulo.
- Detecta el owner del repo raíz desde `remote.origin.url`.
- Convierte URLs de submódulos GitHub del mismo owner a relativas (`../repo.git`), por ejemplo:
  - `git@github.com:johnkespitia/cerradura.git` -> `../cerradura.git`
  - `https://github.com/johnkespitia/cerrajero.git` -> `../cerrajero.git`
- Ejecuta `git submodule sync --recursive` si hubo cambios.
- Ejecuta siempre `git submodule update --init --recursive`.

Además, el hook versionado `scripts/git-hooks/pre-push` ejecuta:

```bash
./scripts/ci/normalize_gitmodules.sh --check-only
```

para bloquear pushes con punteros de submódulos que todavía no existen en remoto.

### Configuración requerida en GitHub

1. Crear un PAT con permisos de lectura de contenido sobre los repos necesarios.
2. Guardarlo como secret del repo con nombre `GH_PAT`.
3. Confirmar que el workflow corre con ese secret disponible.

En el gateway, los intents que requieren repo aceptan codigos resueltos desde
`workspace.config.json`. Para el repo raiz del workspace puedes usar siempre `root`, aunque el
`root_repo` real haya sido renombrado por el bootstrap.
Si un cliente externo no conoce esos codigos, puede descubrirlos con `GET /v1/repos`.

## Modelo operativo

La separación de responsabilidades es esta:

| Capa | Responsabilidad |
|---|---|
| `specs/**` | fuente de verdad funcional y arquitectónica |
| Tessl | disciplina de `spec-first` |
| `flow` | control plane del stack y del SDLC |
| `.flow/**` | estado operativo local |
| `_bmad/` | runtime BMAD del proyecto |
| repos de implementación | código, tests y runtime |

Regla base:

- el root manda en la spec
- los repos implementan
- los agentes leen primero la spec del root y luego bajan al repo correcto

## Flujo mínimo

```bash
python3 ./flow stack design --prompt "quiero una api en golang que se conecte a postgresql y sea consumible usando graphql"
python3 ./flow stack plan
python3 ./flow stack apply
python3 ./flow workflow intake identity-bootstrap --title "Identity Bootstrap" --repo root --runtime go-api --service postgres-service --capability graphql --depends-on spec-as-source-operating-model
python3 ./flow spec review identity-bootstrap
python3 ./flow spec approve identity-bootstrap --approver alice
python3 ./flow workflow execute-feature identity-bootstrap --start-slices --json
python3 ./flow workflow next-step identity-bootstrap --json
python3 ./flow ci spec --all
python3 ./flow release verify --version 2026.03.14-1 --env preview --json
python3 ./flow release status --version 2026.03.14-1
python3 ./flow infra status spec-driven-delivery-bootstrap
python3 ./flow status
```

`flow spec create` ya puede dejar una spec v2 con `schema_version`, `depends_on`, `required_runtimes`, `required_services` y `required_capabilities`. `spec review` y `ci spec` validan esos campos contra los catálogos instalados del workspace.
`flow workflow intake`, `workflow next-step` y `workflow execute-feature` elevan BMAD y Tessl a entrypoint operativo: intake, recomendación de workflow y handoffs para ejecutores/slices.

Puedes forzar el orquestador BMAD de dos formas:

- Configuración persistente en `workspace.config.json`:
  - `project.workflow.default_orchestrator: "bmad"`
  - `project.workflow.force_orchestrator: true`
- Override por comando:
  - `python3 ./flow workflow next-step <spec> --orchestrator bmad --force-orchestrator`

Tambien puedes usar variables de entorno:

- `FLOW_WORKFLOW_ORCHESTRATOR=bmad`
- `FLOW_WORKFLOW_FORCE_ORCHESTRATOR=1`

## Stack local

El devcontainer incluido trae:

- `workspace`: herramientas CLI y edición
- sin repos de implementación por defecto
- sin base de datos por defecto
- runtime packs listos para agregar servicios bajo demanda

Ese stack es intencionalmente mínimo. La topología nace vacía y se expande con `flow add-project`.
Si prefieres un bootstrap declarativo, la topología tambien puede nacer desde `flow stack design`
y materializarse luego con `flow stack apply`, ya sea desde `--prompt` o desde una spec aprobada con `--spec`.

## Comandos útiles

```bash
python3 ./flow --help
python3 ./flow init
python3 ./flow stack design --prompt "quiero una api en golang con postgresql y graphql"
python3 ./flow stack design --spec stack-from-spec
python3 ./flow stack plan --json
python3 ./flow stack plan --spec stack-from-spec --json
python3 ./flow stack apply --json
python3 ./flow stack apply --spec stack-from-spec --json
python3 ./flow add-project mobile --runtime pnpm --port 4173
python3 ./flow stack ps
python3 ./flow stack exec workspace -- pwd
python3 ./flow workspace exec -- python3 ./flow skills doctor
python3 ./flow repo exec sdd-workspace-boilerplate -- python3 ./flow ci spec --all
scripts/workspace_exec.sh python3 ./flow ci spec --all
python3 ./flow tessl -- --help
python3 ./flow bmad -- --help
python3 ./flow ci spec --all
python3 ./flow release cut --version 2026.03.14-1 --spec spec-driven-delivery-bootstrap
python3 ./flow release verify --version 2026.03.14-1 --env preview --json
python3 ./flow release publish --bump auto --dry-run --json
python3 ./flow infra plan spec-driven-delivery-bootstrap --env preview
make help
```

## Documentación

- [docs/softos-agent-dev-handbook.md](docs/softos-agent-dev-handbook.md)
- [docs/spec-driven-orchestration.md](docs/spec-driven-orchestration.md)
- [docs/softos-full-workflow.md](docs/softos-full-workflow.md)
- [docs/flow-json-contract.md](docs/flow-json-contract.md)
- [docs/spec-driven-sdlc-map.md](docs/spec-driven-sdlc-map.md)
- [docs/sdd-implementation-guide.md](docs/sdd-implementation-guide.md)
- [specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md](specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md)
- [specs/000-foundation/spec-as-source-operating-model.spec.md](specs/000-foundation/spec-as-source-operating-model.spec.md)
- [specs/000-foundation/repo-routing-and-worktree-orchestration.spec.md](specs/000-foundation/repo-routing-and-worktree-orchestration.spec.md)

## Licencia

MIT. Ver [LICENSE](LICENSE).
