# Spec-Driven Workspace Boilerplate

Entorno de desarrollo multi-servicio para PLG, orquestado con Docker Compose y devcontainers.

## Arquitectura del entorno

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Compose (red: plg)             │
│                                                         │
│  ┌─────────────┐  ┌──────────┐  ┌──────────┐  ┌──────┐ │
│  │  workspace   │  │ backend  │  │ frontend │  │  db  │ │
│  │             │  │          │  │          │  │      │ │
│  │ PHP 8.2 CLI │  │ PHP 8.2  │  │ Node 20  │  │MySQL │ │
│  │ Node 20     │  │ Composer │  │ pnpm     │  │ 8.0  │ │
│  │ pnpm        │  │ Laravel  │  │ Vite     │  │      │ │
│  │ Composer    │  │          │  │          │  │      │ │
│  │ Tessl CLI   │  │ :8000    │  │ :5173    │  │:3306 │ │
│  │             │  │          │  │          │  │      │ │
│  │ ← Cursor    │  │ /app     │  │ /app     │  │      │ │
│  │   se conecta│  │          │  │          │  │      │ │
│  │   aquí      │  │          │  │          │  │      │ │
│  └─────────────┘  └──────────┘  └──────────┘  └──────┘ │
│        │               │              │           │     │
│        └── /workspace ─┘──────────────┘           │     │
│            (repo completo)                        │     │
│                                              vol: │     │
│                                           mysql-data    │
└─────────────────────────────────────────────────────────┘
```

| Servicio | Imagen base | Monta | Puerto | Propósito |
|---|---|---|---|---|
| `workspace` | Ubuntu 22.04 + PHP + Node + Tessl + BMAD | Todo el repo en `/workspace` | — | Editar código, CLI, git |
| `backend` | php:8.2-cli + extensiones | `backend/` en `/app` | 8000 | Ejecutar Laravel |
| `frontend` | node:20-slim + pnpm | `frontend/` en `/app` | 5173 | Ejecutar Vite |
| `db` | mysql:8.0 | Volumen persistente | 3306 | Base de datos MySQL |

Todos los servicios comparten la red `plg` y se comunican por nombre (e.g. `db:3306` desde backend).

## Estructura del devcontainer

```
.devcontainer/
├── devcontainer.json        # Punto de entrada para Cursor
├── docker-compose.yml       # Orquestación de los 4 servicios
├── Dockerfile               # Imagen del workspace
├── backend.Dockerfile       # Imagen del backend
└── frontend.Dockerfile      # Imagen del frontend
```

## Estructura del workspace

`workspace-root` es un **superproject** con dos submódulos principales:

| Ruta | Tipo | Rol |
|---|---|---|
| `backend/` | submódulo | Backend V2 y código de implementación |
| `frontend/` | submódulo | Frontend V2 y código de implementación |
| `specs/` | root | Fuente de verdad del sistema |
| `.flow/` | root | Estado operativo del SDLC |
| `.tessl/` | root | Guías locales de Tessl para SDD |

Regla importante:

- los cambios backend viven y se branhean desde `backend`
- los cambios frontend viven y se branhean desde `frontend`
- el repo raíz `workspace-root` solo coordina el entorno y actualiza punteros de submódulos cuando corresponde

## Source Of Truth

Este workspace ahora usa un modelo de `Spec As Source` centralizado en el root:

- `specs/**` en `workspace-root` es la fuente de verdad del sistema
- los `targets` de cada spec apuntan a archivos reales del root o de los submódulos
- `backend/` y `frontend/` siguen siendo repos de implementación de código
- `.flow/**` guarda estado operativo, planes y reportes; no reemplaza specs

Esto permite que un agente lea una spec del root y determine automáticamente el repo correcto
viendo sus `targets`.

Consulta [docs/spec-driven-orchestration.md](docs/spec-driven-orchestration.md)
para el flujo operativo.

Para una explicacion completa de la implementacion, sus justificaciones tecnicas, tradeoffs y uso
con submodulos, ver [docs/sdd-implementation-guide.md](docs/sdd-implementation-guide.md).

## Requisitos previos

- Docker Desktop corriendo
- Cursor (o VS Code con la extensión Dev Containers)

## Cómo abrir el proyecto

1. Abre la carpeta `Spec-Driven Workspace Boilerplate` en Cursor
2. Cursor detectará el devcontainer y mostrará **"Reopen in Container"** — haz clic
3. Alternativa: `Cmd+Shift+P` → `Dev Containers: Reopen in Container`
4. La primera vez tardará unos minutos mientras construye las imágenes

Una vez dentro, la terminal estará en `/workspace` con todas las herramientas disponibles:

```bash
php --version      # PHP 8.2
composer --version # Composer 2.x
node --version     # v20.x
pnpm --version     # última versión
tessl --help       # Tessl CLI
```

## Tessl en el root

La disciplina SDD ya no vive en los submódulos. Vive en el root:

- `workspace.config.json`
- `tessl.json`
- `.tessl/RULES.md`
- `.tessl/tiles/workspace/spec-driven-workspace/**`

Esto hace que el equipo clone el repo, abra el devcontainer y tenga el mismo punto de entrada
metodológico desde `workspace-root`.

## Workflow de desarrollo

Este workspace usa un enfoque de **spec-driven development con Tessl** y una capa de
**orquestación por agentes** basada en un CLI del workspace.

La separación de responsabilidades es esta:

| Capa | Herramienta | Responsabilidad |
|---|---|---|
| Fuente de verdad | `specs/**` en el root | Requerimientos funcionales, routing y restricciones de arquitectura |
| Contexto spec-driven | Tessl | Flujo spec-first, tiles, verificación y disciplina de specs |
| Estado operativo | `.flow/**` | Estado del SDLC, planes, reportes y handoffs |
| Orquestación | `python3 ./flow` | Control plane del stack, Tessl, BMAD, planning, slices y contratos operativos |
| Reglas locales | `AGENTS.md` | Lectura obligatoria, alcance de cambios y defaults del repo |

### Source of truth

La fuente de verdad canónica del proyecto es:

- `specs/000-foundation/**`
- `specs/domains/**`
- `specs/features/**`

Los artefactos operativos en `.flow/**` o los reportes generados por prompts **no** reemplazan
esas specs.

Si hay conflicto entre artefactos operativos y specs, prevalece `specs/**`.

### Regla de implementación

La implementación siempre sigue este orden:

1. foundations y feature specs
2. revisión y cierre de decisiones abiertas
3. planning/orquestación por slices
4. implementación
5. tests
6. verificación de drift entre spec, código y tests

No se debe implementar comportamiento que contradiga foundations aprobadas.

### CLI del workspace

El flujo operativo se controla con `python3 ./flow`. `make` actúa como alias humano de esa misma
superficie.

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

BMAD también entra por el mismo control plane:

```bash
python3 ./flow bmad -- --help
```

Si el repo todavía no fue inicializado con BMAD, el CLI ya viene en la imagen pero faltará el
proyecto BMAD local. En ese caso:

```bash
python3 ./flow bmad -- status
python3 ./flow bmad -- install --tools none --yes
```

`_bmad/` queda como instalación versionable del runtime BMAD del proyecto. `_bmad-output/` se trata
como artefacto local derivado.

## Arrancar los servidores de desarrollo

Desde la terminal del workspace:

```bash
# Backend (Laravel)
docker compose exec backend php artisan serve --host=0.0.0.0 --port=8000

# Frontend (Vite)
docker compose exec frontend pnpm dev --host 0.0.0.0
```

## Conexión a MySQL

| Campo | Valor |
|---|---|
| Host | `db` (desde los contenedores) o `localhost` (desde el host) |
| Puerto | `3306` |
| Base de datos | `plg_dev` |
| Usuario | `plg` |
| Contraseña | `plg` |
| Root password | `root` |

Desde el workspace:

```bash
mysql -h db -u plg -pplg plg_dev
```

## Tooling local por submódulo

Los submódulos solo necesitan reglas mínimas de implementación.

Regla de este workspace:

- el root manda en `specs/**`
- el root manda en `.flow/**`
- el root manda en `.tessl/**`
- cada submódulo implementa código dentro de su repo
- un agente baja al submódulo correcto después de leer la spec del root y resolver sus `targets`

Si más adelante un submódulo necesita tooling adicional, ese tooling no debe sustituir ni duplicar
la fuente de verdad del root.

## Herramientas incluidas en workspace

| Herramienta | Versión | Uso |
|---|---|---|
| PHP CLI | 8.2 | Ejecutar comandos artisan, scripts PHP |
| Composer | 2.x | Gestión de dependencias PHP |
| Node.js | 20 LTS | Runtime JavaScript |
| npm | incluido con Node | Gestión de paquetes |
| pnpm | última | Gestión de paquetes (monorepo frontend) |
| Tessl CLI | última | Spec-driven development |
| BMAD CLI | última | Orquestación BMAD desde `flow` |
| git | incluido en base | Control de versiones |
| curl | incluido en base | Requests HTTP |
| unzip | incluido | Descompresión |

## Flujo recomendado

### 1. Abrir en devcontainer

Trabaja preferiblemente dentro del devcontainer. Ahí ya están la topología del workspace y las
herramientas del proyecto.

### 2. Validar el scaffold del root

```bash
make flow-doctor
```

### 3. Crear o continuar una feature

```bash
python3 ./flow spec create identity-bootstrap --title "Identity Bootstrap" --repo backend
python3 ./flow spec review identity-bootstrap
python3 ./flow spec approve identity-bootstrap
python3 ./flow plan identity-bootstrap
```

### 4. Implementar por slices

1. leer la spec del root
2. resolver el repo con `targets`
3. crear la slice y su worktree
4. implementar en el submódulo correcto
5. verificar drift contra la spec

### 5. Mantener `[@test]`

La aprobación y la verificación dependen de `[@test]`. Decláralos en la spec del root usando rutas
relativas al submódulo correspondiente.

## Worktrees y multiagente

La ejecución multiagente recomendada usa `git worktree`, pero desde el submódulo correcto.

Reglas:

- backend: crear worktrees desde `backend`
- frontend: crear worktrees desde `frontend`
- no crear worktrees de backend desde `workspace-root`

Ruta sugerida:

- `flow` usa por defecto `.worktrees/` dentro de `workspace-root`
- esa ruta funciona igual desde el host y dentro del devcontainer
- si necesitas otra topología, define `PLG_WORKTREE_ROOT`

Ejemplo backend dentro del devcontainer:

```bash
git -C /workspace/backend worktree add /workspace/.worktrees/backend-wave1-baseline -b feat/wave1-baseline
```

Ejemplo backend desde el host:

```bash
git -C "$(pwd)/backend" worktree add "$(pwd)/.worktrees/backend-wave1-baseline" -b feat/wave1-baseline
```

Merge correcto:

1. merge en el submódulo `backend`
2. actualizar el puntero del submódulo en `workspace-root`

### Playbook

La guía operativa y la matriz de paralelización viven en:

- [docs/spec-driven-orchestration.md](docs/spec-driven-orchestration.md)
- [specs/000-foundation/spec-as-source-operating-model.spec.md](specs/000-foundation/spec-as-source-operating-model.spec.md)
- [specs/000-foundation/repo-routing-and-worktree-orchestration.spec.md](specs/000-foundation/repo-routing-and-worktree-orchestration.spec.md)

## Extensiones de Cursor / VS Code

Se instalan automáticamente al abrir el devcontainer:

- **Intelephense** — IntelliSense para PHP
- **ESLint** — Linting JavaScript/TypeScript
- **Prettier** — Formateo de código
- **DotENV** — Soporte para archivos `.env`
- **Docker** — Gestión de contenedores

## Decisiones de diseño

**Workspace separado de backend/frontend** — Cursor edita en workspace; los servicios ejecutan el código de forma aislada. Ningún servicio mezcla responsabilidades.

**`sleep infinity` en workspace, backend y frontend** — Son contenedores de desarrollo que deben permanecer vivos para ejecutar comandos manualmente. MySQL no lo necesita porque su daemon ya corre por defecto.

**Tessl via npm dentro del contenedor** — El instalador nativo (`curl -fsSL https://get.tessl.io | sh`) pone binarios en `~/.local/bin` del usuario que ejecuta el script. En Docker con usuario `vscode`, eso complica el PATH. `npm install -g @tessl/cli` lo coloca en una ruta global accesible.

**Healthcheck en MySQL** — El backend usa `depends_on: condition: service_healthy`, garantizando que MySQL acepta conexiones antes de que el backend inicie.

**Volúmenes con `:cached`** — En macOS, `:cached` mejora el rendimiento de I/O al montar código fuente desde el host.

**3 Dockerfiles separados** — Cada servicio tiene exactamente lo que necesita. El workspace tiene todas las herramientas CLI. Backend y frontend solo tienen su runtime.

**`shutdownAction: stopCompose`** — Al cerrar Cursor, se detienen todos los servicios. No quedan contenedores huérfanos.

**Spec As Source centralizado** — las specs viven en el root y apuntan por `targets` hacia el repo de implementación correcto. El workspace no depende de prompts sueltos como mecanismo principal.

**Tessl + flow CLI** — Tessl disciplina el SDD; `flow` es el control plane del workspace. Desde ahí
entran stack, Tessl, BMAD, estado operativo, planes y handoffs. Si un submódulo usa BMAD u otro
orquestador local, sigue subordinado a la spec del root.

## Ajustes manuales necesarios

1. **`tessl login`** — Ejecutar dentro del workspace para autenticarte con Tessl
2. **Credenciales de MySQL** — Los valores actuales (`plg/plg`) son para desarrollo local. Si la base legacy necesita otros valores, edita la sección `environment` del servicio `db` en `docker-compose.yml`
3. **Tooling local de código** — Si un repo necesita herramientas de lenguaje o framework, instálalas dentro de ese submódulo, nunca como sustituto del root `specs/**`.

## Stack

- **Backend**: PHP 8.2 + Laravel 11
- **Frontend**: Vite + React (monorepo con pnpm)
- **Base de datos**: MySQL 8.0
- **Workflow**: Spec-driven development con Tessl + orquestación con `flow`
- **Herramientas**: Cursor, Codex, Tessl, `flow`
