# Spec-Driven Orchestration

Este workspace usa un modelo de `Spec As Source` centralizado en el root y una capa operativa
ligera para orquestar el SDLC.

Nota:

- el boilerplate nace con solo `workspace`
- los nombres `backend` y `frontend` en este documento son ejemplos de repos agregados despues con
  `python3 ./flow add-project ...`

## Principios

- `specs/**` en `workspace-root` es la fuente de verdad del sistema.
- Los submodulos son repos de implementacion.
- `.flow/**` guarda estado operativo y reportes, no requerimientos.
- El repo de implementacion se deduce desde `targets`.
- Los `targets` invalidos fallan cerrado; no se enrutan por heuristica silenciosa.

## Routing por targets

Ejemplos validos en una spec del root:

- `../../backend/app/**`
- `../../backend/tests/**`
- `../../frontend/src/**`
- `../../.devcontainer/**`

Con esto un agente puede decidir donde aplicar el trabajo sin necesidad de rutas codificadas a
mano. Si un `target` apunta a un root no permitido, `flow` corta el proceso.

## CLI

El workspace expone `python3 ./flow` como control plane.

### Comandos

```bash
python3 ./flow stack doctor
python3 ./flow stack ps
python3 ./flow stack design --prompt "quiero una api en golang con postgresql y graphql"
python3 ./flow stack plan --json
python3 ./flow stack apply --json
python3 ./flow tessl -- --help
python3 ./flow skills doctor
python3 ./flow skills sync --dry-run
python3 ./flow secrets doctor
python3 ./flow secrets sync --dry-run
python3 ./flow providers doctor
python3 ./flow submodule doctor --json
python3 ./flow doctor
python3 ./flow add-project backend --runtime php --port 8000
python3 ./flow add-project frontend --runtime pnpm --port 5173
python3 ./flow spec create identity-bootstrap --title "Identity Bootstrap" --repo backend
python3 ./flow spec review identity-bootstrap
python3 ./flow spec approve identity-bootstrap
python3 ./flow plan identity-bootstrap
python3 ./flow slice start identity-bootstrap backend-main
python3 ./flow slice verify identity-bootstrap backend-main
python3 ./flow drift check --all --json
python3 ./flow spec generate-contracts spec-driven-delivery-bootstrap --json
python3 ./flow ci spec --all
python3 ./flow ci repo --all
python3 ./flow ci integration --profile smoke
python3 ./flow release status --version 2026.03.14-1
python3 ./flow infra status identity-bootstrap
python3 ./flow status
```

BMAD también se invoca desde el mismo control plane:

```bash
python3 ./flow bmad -- --help
python3 ./flow bmad -- status
python3 ./flow bmad -- install --tools none --yes
```

## Flujo

1. crear spec
2. revisar spec
3. aprobar spec
4. generar plan por repo o slice
5. arrancar slice en worktree
6. verificar slice con checks estructurales reales
7. correr CI del root y del repo afectado
8. cortar release y promover desde el root cuando corresponda

## Stack y adapters

- `flow stack ...` resuelve el proyecto Compose correcto del devcontainer y evita depender del
  nombre implícito del host.
- `flow stack design|plan|apply` permite partir de un chasis root-only y materializar proyectos,
  servicios standalone y foundations derivadas sin editar manifests a mano.
- `flow tessl ...` ejecuta Tessl en el entorno canónico del `workspace`.
- `flow skills ...` usa `workspace.skills.json` como manifest versionado para sincronizar skills
  de Tessl y `skills.sh` sin depender de `~/.codex/**`.
- `workspace.skills.json` queda reservado para capacidades del agente; el scaffolding de proyectos
  ahora sale de `workspace.runtimes.json` y `runtimes/*.runtime.json`.
- `flow secrets ...` usa `workspace.secrets.json` y adapters por provider para generar archivos
  locales gitignored o ejecutar comandos con secretos inyectados sin acoplarse a una plataforma.
- `flow providers ...` usa `workspace.providers.json` para resolver adapters de release e infra sin
  acoplar `flow` a una plataforma de despliegue específica.
- `flow submodule ...` añade guardrails explícitos para punteros Git cuando un workspace usa
  submódulos; en un boilerplate con repos `plain`, el comando degrada a no-op.
- `flow bmad ...` resuelve BMAD dentro del `workspace`, ejecuta en `/workspace` y permite inicializar
  `_bmad/` con `install` cuando el proyecto aún no fue bootstrappeado.
- `_bmad/` se versiona como runtime/configuración del proyecto; `_bmad-output/` queda como artefacto
  local derivado.
- `make` delega en `flow`; no es una segunda fuente de lógica.

## Convenciones

### Feature slug

`kebab-case`

### Branches

`feat/<feature>-<slice>`

### Worktrees

`<workspace>/.worktrees/<repo>-<feature>-<slice>`

`flow` usa por defecto `.worktrees/` dentro del workspace para que el comando funcione igual en el
host y dentro del devcontainer. Si hiciera falta otra ruta, se puede sobreescribir con
`FLOW_WORKTREE_ROOT`.

## Regla de drift

Si cambia el comportamiento, cambia la spec en el mismo cambio. Si un test nuevo no esta
enlazado desde la spec, el cambio esta incompleto.

## Contratos derivados

Los contratos ejecutables no son una segunda fuente de verdad. Se derivan desde bloques
`json contract` en las specs y se materializan en `contracts/generated/**` con:

```bash
python3 ./flow spec generate-contracts <spec> --json
```
