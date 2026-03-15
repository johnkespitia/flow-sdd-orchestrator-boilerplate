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

- `flow`: CLI del workspace para `stack`, `tessl`, `skills`, `bmad`, `add-project`, `spec`, `plan`, `slice`, `ci`, `release`, `infra`, `status`
- `workspace.config.json`: routing configurable de repos, targets y test runners
- `workspace.skills.json`: manifest versionado de skills y tiles del workspace
- `.tessl/**`: tile local de SDD centrado en root
- `_bmad/`: instalación versionada del runtime BMAD del proyecto
- `.flow/**`: estado operativo local del SDLC
- `.devcontainer/**`: stack reproducible con `workspace`, `backend`, `frontend` y `db`
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
- `backend/` y `frontend/` placeholder
- stack base `PHP + Node + MySQL`
- comandos de instalación por defecto del `Makefile`

## Uso recomendado

### Opción 1: usar este repo como template

1. En GitHub usa `Use this template`
2. Crea tu nuevo repo
3. Clona el repo nuevo
4. Ajusta nombres y repos con `bootstrap_workspace.py` si todavía quieres renombrar la topología

### Opción 2: generar un proyecto aislado desde este repo

Desde este boilerplate:

```bash
python3 scripts/bootstrap_workspace.py /ruta/al/nuevo-workspace \
  --project-name "Acme Platform" \
  --root-repo acme-dev-env \
  --backend-repo platform-api \
  --frontend-repo platform-web \
  --git-init
```

Eso genera un workspace nuevo:

- con su propio `.git`
- con `workspace.config.json` ya ajustado
- con placeholders limpios para los repos de implementación
- sin arrastrar estado operativo previo

## Después de crear tu workspace

1. Reemplaza `backend/` y `frontend/` por repos reales o submódulos Git
2. Ajusta [`workspace.config.json`](workspace.config.json) a tus repos y roots válidos
3. Si tu stack no es `PHP + Node + MySQL`, cambia [`.devcontainer/docker-compose.yml`](.devcontainer/docker-compose.yml) y los Dockerfiles
4. Abre el root en devcontainer
5. Ejecuta:

Nota:

- `devcontainer.json` añade mounts y variables para que `python3 ./flow stack ...` y
  `python3 ./flow doctor` funcionen tambien desde dentro del `workspace`
- si cambias `.devcontainer/**`, usa **Rebuild Container**; un `docker compose up` directo no aplica
  toda la capa extra que inyecta Cursor/VS Code

```bash
python3 ./flow doctor
python3 ./flow stack doctor
python3 ./flow tessl -- --help
python3 ./flow skills doctor
python3 ./flow bmad -- status
python3 ./flow ci spec --all
python3 ./flow release --help
python3 ./flow infra --help
```

Si necesitas un tercer proyecto de implementación, puedes registrarlo desde el control plane:

```bash
python3 ./flow add-project mobile --runtime pnpm --port 4173
```

Eso actualiza `workspace.config.json`, crea el directorio placeholder y, si el runtime lo soporta,
agrega un servicio al `docker-compose` del devcontainer.

Las skills y tiles del workspace también se gobiernan desde el control plane:

```bash
python3 ./flow skills doctor
python3 ./flow skills list
python3 ./flow skills sync --dry-run
python3 ./flow skills add team-review --provider skills-sh --source your-org/agent-skills --arg=--copy
```

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
python3 ./flow spec create identity-bootstrap --title "Identity Bootstrap" --repo backend
python3 ./flow spec review identity-bootstrap
python3 ./flow spec approve identity-bootstrap
python3 ./flow plan identity-bootstrap
python3 ./flow slice start identity-bootstrap backend-main
python3 ./flow slice verify identity-bootstrap backend-main
python3 ./flow ci spec --all
python3 ./flow release status --version 2026.03.14-1
python3 ./flow infra status spec-driven-delivery-bootstrap
python3 ./flow status
```

## Stack local

El devcontainer incluido trae:

- `workspace`: herramientas CLI y edición
- `backend`: placeholder de runtime backend
- `frontend`: placeholder de runtime frontend
- `db`: MySQL local

Ese stack es solo una base de arranque. Si tu proyecto usa otra topología, cámbiala.

## Comandos útiles

```bash
python3 ./flow --help
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
- [docs/spec-driven-sdlc-map.md](docs/spec-driven-sdlc-map.md)
- [docs/sdd-implementation-guide.md](docs/sdd-implementation-guide.md)
- [specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md](specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md)
- [specs/000-foundation/spec-as-source-operating-model.spec.md](specs/000-foundation/spec-as-source-operating-model.spec.md)
- [specs/000-foundation/repo-routing-and-worktree-orchestration.spec.md](specs/000-foundation/repo-routing-and-worktree-orchestration.spec.md)

## Licencia

MIT. Ver [LICENSE](LICENSE).
