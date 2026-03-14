# Spec-Driven Orchestration

Este workspace usa un modelo de `Spec As Source` centralizado en el root y una capa operativa
ligera para orquestar el SDLC.

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
python3 ./flow tessl -- --help
python3 ./flow doctor
python3 ./flow spec create identity-bootstrap --title "Identity Bootstrap" --repo backend
python3 ./flow spec review identity-bootstrap
python3 ./flow spec approve identity-bootstrap
python3 ./flow plan identity-bootstrap
python3 ./flow slice start identity-bootstrap backend-main
python3 ./flow slice verify identity-bootstrap backend-main
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
7. mergear cuando pase review y QA

## Stack y adapters

- `flow stack ...` resuelve el proyecto Compose correcto del devcontainer y evita depender del
  nombre implícito del host.
- `flow tessl ...` ejecuta Tessl en el entorno canónico del `workspace`.
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
