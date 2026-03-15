# Flow SDD Orchestrator Boilerplate

Template repo para levantar un workspace de `Spec As Source` con:

- `specs/**` como fuente de verdad
- `flow` como control plane del SDLC y del stack
- Tessl como capa metodológica de SDD
- BMAD como runtime de orquestación opcional pero ya integrado
- devcontainer reproducible para el equipo
- repos de implementación separados del root del workspace

No es un producto específico. Es una base reusable para crear workspaces agentic y spec-driven.

## Qué trae

- `flow`: CLI del workspace para `stack`, `tessl`, `skills`, `bmad`, `add-project`, `spec`, `plan`, `slice`, `ci`, `release`, `infra`, `submodule`, `secrets`, `drift`, `status`
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

## Después de crear tu workspace

1. Abre el root en devcontainer
2. Valida el scaffold
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
python3 ./flow doctor
python3 ./flow stack doctor
python3 ./flow tessl -- --help
python3 ./flow skills doctor
python3 ./flow secrets doctor
python3 ./flow secrets scan --all --json
python3 ./flow providers doctor
python3 ./flow bmad -- status
python3 ./flow submodule doctor --json
python3 ./flow ci spec --all
python3 ./flow drift check --all --json
python3 ./flow contract verify --all --json
python3 ./flow spec generate-contracts spec-driven-delivery-bootstrap --json
python3 ./flow release --help
python3 ./flow infra --help
```

Si necesitas un tercer proyecto de implementación, puedes registrarlo desde el control plane:

```bash
python3 ./flow add-project api --runtime php --port 8000
python3 ./flow add-project web --runtime pnpm --port 5173
python3 ./flow add-project mobile --runtime pnpm --port 4173
```

Eso actualiza `workspace.config.json`, crea el directorio placeholder y, si el runtime lo soporta,
agrega el servicio al `docker-compose` del devcontainer junto con auxiliares del runtime. El
runtime `php`, por ejemplo, agrega `db` si todavía no existe.

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

Arranque basico:

```bash
python3 ./flow secrets sync
python3 ./flow stack up
docker compose exec gateway curl -fsSL http://127.0.0.1:8010/healthz
```

Las skills y tiles del workspace también se gobiernan desde el control plane:

```bash
python3 ./flow skills doctor
python3 ./flow skills list
python3 ./flow skills sync --dry-run
python3 ./flow skills add team-review --provider skills-sh --source your-org/agent-skills --arg=--copy
python3 ./flow skills add github-review --provider skills-sh --source your-org/agent-skills --require gh
```

Los runtimes de `flow add-project` se resuelven desde `workspace.runtimes.json` y `runtimes/*.runtime.json`,
dejando `workspace.skills.json` reservado para capacidades del agente:

```bash
python3 ./flow add-project api --runtime php --port 8000
python3 ./flow add-project web --runtime pnpm --port 5173
```

Los providers de CD e infraestructura se gobiernan igual:

```bash
python3 ./flow providers doctor
python3 ./flow providers list
python3 ./flow release promote --version 2026.03.14-1 --env preview --provider local-hooks
python3 ./flow infra plan spec-driven-delivery-bootstrap --env preview --provider local-hooks
```

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
python3 ./flow spec create identity-bootstrap --title "Identity Bootstrap" --repo api
python3 ./flow spec review identity-bootstrap
python3 ./flow spec approve identity-bootstrap
python3 ./flow plan identity-bootstrap
python3 ./flow slice start identity-bootstrap api-main
python3 ./flow slice verify identity-bootstrap api-main
python3 ./flow ci spec --all
python3 ./flow release status --version 2026.03.14-1
python3 ./flow infra status spec-driven-delivery-bootstrap
python3 ./flow status
```

## Stack local

El devcontainer incluido trae:

- `workspace`: herramientas CLI y edición
- sin repos de implementación por defecto
- sin base de datos por defecto
- runtime packs listos para agregar servicios bajo demanda

Ese stack es intencionalmente mínimo. La topología nace vacía y se expande con `flow add-project`.
Si prefieres un bootstrap declarativo, la topología tambien puede nacer desde `flow stack design`
y materializarse luego con `flow stack apply`.

## Comandos útiles

```bash
python3 ./flow --help
python3 ./flow stack design --prompt "quiero una api en golang con postgresql y graphql"
python3 ./flow stack plan --json
python3 ./flow stack apply --json
python3 ./flow add-project mobile --runtime pnpm --port 4173
python3 ./flow stack ps
python3 ./flow tessl -- --help
python3 ./flow bmad -- --help
python3 ./flow ci spec --all
python3 ./flow release cut --version 2026.03.14-1 --spec spec-driven-delivery-bootstrap
python3 ./flow infra plan spec-driven-delivery-bootstrap --env preview
make help
```

## Documentación

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
