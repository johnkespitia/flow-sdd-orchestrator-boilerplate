---
schema_version: 3
name: "Runtime user ownership"
description: "Corregir la propiedad de archivos en bind mounts del workspace garantizando que el servicio workspace y las rutas de ejecución canónicas de SoftOS operen como usuario de desarrollo (FLOW_WORKSPACE_USER, default vscode) mientras root queda reservado solo para preparación de arranque del contenedor."
status: draft
owner: platform
single_slice_reason: "Bugfix transversal del contrato de ownership entre compose, entrypoint y flowctl con validación ya demostrada en este worktree."
multi_domain: false
phases: []
depends_on:
  - specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
  - specs/features/spec-driven-delivery-bootstrap.spec.md
required_runtimes:
  - python
required_services:
  - workspace
stack_projects: []
stack_services: []
stack_capabilities: []
targets:
  - ../../.devcontainer/docker-compose.yml
  - ../../.devcontainer/workspace-entrypoint.sh
  - ../../flow
  - ../../flowctl/stack_ops.py
  - ../../flowctl/tooling.py
  - ../../flowctl/test_workspace_exec_user.py
  - ../../specs/features/runtime-user-ownership.spec.md
---

# Runtime user ownership

## Objetivo

Garantizar que las operaciones normales de SoftOS sobre el workspace montado desde el host no
dejen archivos propiedad de `root` en bind mounts de workspace/worktrees, preservando al mismo
tiempo acceso funcional a `docker.sock` y el contrato de usuario propio de servicios compose que
no son `workspace`.

El servicio `workspace` (y `gateway`, que comparte el mismo contrato de arranque) debe iniciar
como `root` únicamente el tiempo necesario para preparar acceso suplementario al socket Docker y,
acto seguido, ejecutar su comando principal como `FLOW_WORKSPACE_USER` (default `vscode`) usando
`setpriv`, de modo que PID 1 del servicio sea el usuario de desarrollo.

Las rutas de ejecución canónicas de SoftOS (`flow workspace exec`, `flow repo exec` cuando el
servicio resuelto es `workspace`, `flow stack exec`/`flow stack sh` cuando el servicio objetivo es
`workspace`, y `wrap_repo_command_for_service` bajo la misma regla) deben entrar al contenedor
como usuario de desarrollo. Los servicios compose distintos de `workspace` conservan su contrato
de usuario existente.

## Contexto

- SoftOS monta el workspace y worktrees del host dentro de contenedores Docker.
- El bind mount hace que UID/GID dentro del contenedor se reflejen directamente en el filesystem
  del host.
- Antes de este fix, el servicio `workspace` y las invocaciones canónicas podían ejecutar como
  `root`, creando archivos `root`-owned en rutas compartidas con el operador del host.
- La validación real en este worktree demostró el contrato objetivo:
  - PID 1 de `workspace` = `vscode` UID/GID 1000
  - PID 1 de `gateway` = `vscode` UID/GID 1000
  - `flow stack exec workspace id` = `vscode` UID/GID 1000 con grupo suplementario `docker-host`
  - archivos creados vía SoftOS en el bind mount aparecen como `john:john` UID/GID 1000 en el host
  - tests focalizados de ownership/tooling = 23 passed
  - suite completa `flowctl` = 263 passed, 73 subtests passed, con 5 fallos preexistentes/sensibles
    al entorno no relacionados con este cambio
- `setpriv` ya existe en la imagen; no se requiere paquete nuevo.

## Foundations Aplicables

- `specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md`
- `specs/features/spec-driven-delivery-bootstrap.spec.md` (entrypoints canónicos `flow workspace exec`
  y `flow repo exec`)

## Domains Aplicables

- no aplica domain porque el cambio es contrato operativo del runtime/devcontainer y control plane,
  no vocabulario de producto

## Problema a resolver

### Síntoma

Operaciones rutinarias del desarrollador vía SoftOS (tests, generación de artefactos, edición desde
el devcontainer) producían archivos y directorios propiedad de `root` en el workspace/worktrees
montados desde el host. Eso obligaba a `chown` manual, rompía permisos del operador host y
confundía la frontera entre ejecución administrativa y desarrollo.

### Causa raíz

1. El servicio `workspace` en compose arrancaba y permanecía como `root` para todo el ciclo de
   vida del contenedor.
2. Las rutas canónicas de ejecución (`flow workspace exec`, partes de `flow repo exec`,
   `flow stack exec`/`sh`, y envoltorios compose en `flow`) no forzaban usuario de desarrollo
   de forma consistente cuando el servicio objetivo era `workspace`.
3. La preparación de acceso a `docker.sock` (grupo suplementario del socket) estaba acoplada a
   ejecución prolongada como `root` en lugar de limitarse a bootstrap de arranque.

## Alcance

### Incluye

- arrancar `workspace` y `gateway` como `root` solo durante preparación de arranque en
  `.devcontainer/workspace-entrypoint.sh`
- preparar antes del `setpriv` las rutas exactas de estado del usuario de desarrollo
  (`.local`, `.local/share`, `.local/share/tessl`, `.local/share/pnpm`,
  `.local/share/pnpm/store`, `.config`, `.cache`) con ownership del usuario objetivo
- después del bootstrap, re-ejecutar el comando del servicio como `FLOW_WORKSPACE_USER` (default
  `vscode`) vía `setpriv --reuid --regid --init-groups`
- declarar `user: root` en compose únicamente para habilitar esa preparación inicial; el proceso
  principal del servicio debe quedar bajo el usuario de desarrollo
- preservar acceso suplementario a `docker.sock` (`docker-host` o grupo equivalente del GID del
  socket) para el usuario de desarrollo
- `flow workspace exec` siempre delega al servicio `workspace` con usuario de desarrollo
- `flow repo exec` usa usuario de desarrollo solo cuando el `compose_service` resuelto es
  `workspace`; servicios de repo distintos no reciben `--user` impuesto por SoftOS
- `flow stack exec` y `flow stack sh` usan usuario de desarrollo solo cuando el servicio
  objetivo es `workspace`
- `wrap_repo_command_for_service` en `flow` sigue la misma regla workspace-only
- pruebas de regresión en `flowctl/test_workspace_exec_user.py`
- esta spec como fuente de verdad del contrato

### No incluye

- imponer `vscode` o `FLOW_WORKSPACE_USER` a servicios compose que no son `workspace`
- cambiar el contrato de usuario de servicios de implementación (backend, frontend, bases de datos,
  etc.)
- garantizar ejecución non-root cuando el operador usa `docker compose exec` directamente sin
  pasar por SoftOS (escape hatch administrativo)
- cambios BMAD, orchestrator, workflow runner o gateway intake
- nuevos paquetes de imagen; `setpriv` ya está disponible
- modificar archivos fuera de `targets`

## Repos afectados

| Repo | Targets |
| --- | --- |
| `sdd-workspace-boilerplate` | `../../.devcontainer/docker-compose.yml`, `../../.devcontainer/workspace-entrypoint.sh`, `../../flow`, `../../flowctl/stack_ops.py`, `../../flowctl/tooling.py`, `../../flowctl/test_workspace_exec_user.py`, `../../specs/features/runtime-user-ownership.spec.md` |

## Resultado esperado

- PID 1 de `workspace` y `gateway` corre como `FLOW_WORKSPACE_USER` (default `vscode`)
- `flow workspace exec`, `flow repo exec` (servicio `workspace`), `flow stack exec workspace`,
  `flow stack sh workspace` y envoltorios compose equivalentes entran como usuario de desarrollo
- archivos creados por esas rutas en bind mounts aparecen con UID/GID del operador host, no como
  `root`
- el usuario de desarrollo mantiene grupo suplementario para `docker.sock`
- servicios no-workspace conservan su usuario compose/configurado sin override SoftOS
- `FLOW_WORKSPACE_USER` sigue siendo overrideable por entorno

## Contrato de ownership en runtime

### Bootstrap de contenedor (root permitido)

El entrypoint `/usr/local/share/flow/workspace-entrypoint.sh` puede ejecutarse como `root` solo
para:

1. detectar el GID de `/var/run/docker.sock`
2. asegurar un grupo (`docker-host` o el grupo existente del socket) y añadir
   `FLOW_WORKSPACE_USER` a ese grupo
3. calcular `target_uid`/`target_gid` del usuario de desarrollo
4. crear y asignar ownership solo a las rutas exactas de estado del usuario de desarrollo
   necesarias para Tessl, BMAD, pnpm, config y cache

Ninguna otra operación rutinaria del servicio debe depender de permisos de `root` después de este
bootstrap.

### Proceso principal del servicio

Si el entrypoint corre como `root`, el usuario objetivo existe y no es `root`, el entrypoint debe
terminar con:

```bash
exec setpriv --reuid="$target_uid" --regid="$target_gid" --init-groups -- "$@"
```

de modo que PID 1 del servicio sea el usuario de desarrollo con grupos inicializados (incluido el
suplementario de `docker.sock`).

### Override de usuario

- variable canónica: `FLOW_WORKSPACE_USER`
- default: `vscode`
- resolución centralizada en `flowctl/context.py` (`workspace_exec_user()`)
- el override no debe reintroducir ejecución prolongada como `root` salvo que el operador elija
  explícitamente `root` como valor (fuera del contrato normal de desarrollo)

### Servicios fuera de workspace

Los servicios compose distintos de `workspace` no adoptan `FLOW_WORKSPACE_USER`. SoftOS no debe
inyectar `--user` en `compose exec` para esos servicios.

## Comportamiento de rutas de ejecución canónicas

| Ruta | Servicio objetivo | Usuario de ejecución | Notas |
| --- | --- | --- | --- |
| `flow workspace exec -- <cmd>` | `workspace` | `FLOW_WORKSPACE_USER` | siempre |
| `flow repo exec <repo> -- <cmd>` | resuelto = `workspace` | `FLOW_WORKSPACE_USER` | solo si el compose service del repo es `workspace` |
| `flow repo exec <repo> -- <cmd>` | resuelto ≠ `workspace` | sin override SoftOS | conserva contrato del servicio |
| `flow stack exec workspace -- <cmd>` | `workspace` | `FLOW_WORKSPACE_USER` | incluye TTY/no-TTY |
| `flow stack sh workspace` | `workspace` | `FLOW_WORKSPACE_USER` | shell interactivo |
| `flow stack exec <svc> -- <cmd>` | `<svc>` ≠ `workspace` | sin override SoftOS | conserva contrato del servicio |
| `flow stack sh <svc>` | `<svc>` ≠ `workspace` | sin override SoftOS | conserva contrato del servicio |
| `wrap_repo_command_for_service(...)` | resuelto = `workspace` | `FLOW_WORKSPACE_USER` vía `compose exec --user` | usado por CI/repo tooling |
| `wrap_repo_command_for_service(...)` | resuelto ≠ `workspace` | sin override SoftOS | |
| `docker compose exec ...` directo | cualquiera | no gobernado | escape hatch administrativo; puede entrar como root |

Cuando la invocación ya ocurre dentro del devcontainer (`running_inside_workspace()`), los
comandos locales no re-envuelven compose innecesariamente; el contrato de ownership se cumple
porque PID 1 del servicio ya es el usuario de desarrollo.

## Seguridad e invariantes

### Invariantes obligatorios

1. **Root solo en bootstrap**: `root` está permitido únicamente para preparación de arranque del
   contenedor (acceso a `docker.sock`), no para operaciones normales de desarrollo.
2. **Sin archivos root-owned en mounts compartidos**: las rutas canónicas de SoftOS sobre
   workspace/worktrees no deben crear archivos propiedad de `root` en bind mounts.
3. **Workspace-only user forcing**: SoftOS no fuerza `FLOW_WORKSPACE_USER` sobre servicios que no
   son `workspace`.
4. **Docker.sock preservado**: el usuario de desarrollo debe conservar acceso funcional al daemon
   Docker del host vía grupo suplementario del socket.
5. **Sin paquetes nuevos**: usar `setpriv` existente; no introducir dependencias adicionales de
   imagen para este contrato.
6. **Sin cambios BMAD/orchestrator**: el fix es runtime/control-plane, no orquestación multi-agente.
7. **Escape hatch explícito**: `docker compose exec` directo queda fuera del contrato garantizado;
   puede seguir entrando como `root` y no se considera regresión de SoftOS.

### Prohibiciones

- no eliminar ni degradar acceso a `docker.sock`
- no convertir servicios de implementación a `vscode` por defecto
- no expandir `targets` más allá de los declarados en frontmatter
- no aprobar ni promover release de esta spec en el mismo cambio que la redacción inicial draft

## Reglas de negocio

- la spec aprobada gobierna el contrato de ownership; `.flow/**` es evidencia operativa, no fuente
  de verdad
- el operador host debe poder editar/borrar artefactos creados por SoftOS sin intervención
  administrativa
- cambiar `FLOW_WORKSPACE_USER` debe afectar de forma coherente entrypoint, compose exec y tests
  asociados

## Flujo principal

1. Compose arranca `workspace`/`gateway` con `user: root` y entrypoint compartido.
2. Entrypoint prepara grupo suplementario de `docker.sock` para `FLOW_WORKSPACE_USER`.
3. Entrypoint hace `setpriv` al usuario de desarrollo y ejecuta el comando del servicio.
4. Desde host, `flow workspace exec`/`repo exec`/`stack exec` resuelven servicio y aplican
   `--user` solo cuando el servicio es `workspace`.
5. Archivos creados en bind mounts heredan UID/GID del usuario de desarrollo.
6. Tests en `test_workspace_exec_user.py` fijan el contrato para entrypoint, tooling y stack ops.

## Contrato funcional

- **inputs clave**: `FLOW_WORKSPACE_USER`, servicio compose resuelto, comando passthrough, bind
  mounts host↔contenedor
- **outputs clave**: procesos bajo UID/GID de desarrollo, archivos host con ownership del operador,
  acceso docker funcional
- **errores esperados**: si `FLOW_WORKSPACE_USER` no existe en imagen, el entrypoint no debe
  hacer `setpriv` y debe fallar de forma explícita o documentada (comportamiento actual: solo
  `setpriv` cuando el usuario existe)
- **side effects relevantes**: membresía de grupo suplementario persistida en el contenedor para el
  usuario de desarrollo durante el ciclo de vida del servicio

## Routing de implementacion

- El repo se deduce desde `targets`: `sdd-workspace-boilerplate`.
- Una sola slice material cubre compose, entrypoint, `flow`, `flowctl` y tests.
- El plan operativo vive en `.flow/plans/**` si se materializa; esta spec documenta trabajo ya
  validado en el worktree activo.
- No editar archivos fuera de `targets`.

## Slice Breakdown

```yaml
- name: runtime-user-ownership-fix
  repo: sdd-workspace-boilerplate
  targets:
    - ../../.devcontainer/docker-compose.yml
    - ../../.devcontainer/workspace-entrypoint.sh
    - ../../flow
    - ../../flowctl/stack_ops.py
    - ../../flowctl/tooling.py
    - ../../flowctl/test_workspace_exec_user.py
    - ../../specs/features/runtime-user-ownership.spec.md
  hot_area: devcontainer/runtime-ownership
  depends_on: []
```

## Criterios de aceptacion

- `workspace` PID 1 corre como `FLOW_WORKSPACE_USER` (default `vscode`, UID/GID 1000 en imagen
  estándar)
- `gateway` PID 1 corre como `FLOW_WORKSPACE_USER` con el mismo contrato de entrypoint
- `flow stack exec workspace -- id` reporta UID/GID del usuario de desarrollo y pertenencia al
  grupo suplementario de `docker.sock`
- archivos creados vía rutas canónicas de SoftOS en bind mounts aparecen en el host con ownership
  del operador (p. ej. `john:john` cuando UID/GID 1000 coincide)
- `flow repo exec` no fuerza `--user` cuando el servicio resuelto no es `workspace`
- `flow stack exec`/`flow stack sh` no fuerzan `--user` para servicios distintos de `workspace`
- `wrap_repo_command_for_service` aplica la regla workspace-only
- `FLOW_WORKSPACE_USER` overrideable y respetado por entrypoint y tooling
- `python3 ./flow ci spec specs/features/runtime-user-ownership.spec.md --json` pasa tras aprobar
  la spec
- tests focalizados: 23 passed en `flowctl/test_workspace_exec_user.py` y módulos de ownership
  relacionados
- suite `flowctl` completa: 263 passed, 73 subtests passed; fallos restantes documentados como
  preexistentes/no relacionados

## Verification Matrix

```yaml
- name: workspace-pid1-non-root
  level: smoke
  command: python3 ./flow stack exec workspace -- sh -lc 'ps -o user=,pid= -p 1'
  blocking_on:
    - ci
  environments:
    - local
  notes: PID 1 del servicio workspace debe ser FLOW_WORKSPACE_USER (default vscode)

- name: gateway-pid1-non-root
  level: smoke
  command: python3 ./flow stack exec gateway -- sh -lc 'ps -o user=,pid= -p 1'
  blocking_on:
    - ci
  environments:
    - local
  notes: gateway comparte entrypoint y debe dropear privilegios igual que workspace

- name: stack-exec-workspace-id
  level: smoke
  command: python3 ./flow stack exec workspace -- sh -lc 'id'
  blocking_on:
    - ci
  environments:
    - local
  notes: debe mostrar uid/gid del usuario de desarrollo y grupo suplementario docker-host

- name: workspace-exec-user-ownership-tests
  level: integration
  command: scripts/workspace_exec.sh python3 -m pytest flowctl/test_workspace_exec_user.py -q
  blocking_on:
    - ci
    - release
  environments:
    - local
  notes: regresión automatizada del contrato entrypoint + tooling + stack ops

- name: flowctl-suite-regression
  level: integration
  command: scripts/workspace_exec.sh python3 -m pytest flowctl -q
  blocking_on:
    - ci
  environments:
    - local
  notes: suite amplia; tolera fallos preexistentes/sensibles al entorno no relacionados con ownership
```

## Test plan

- [@test] ../../flowctl/test_workspace_exec_user.py

## Rollout

1. Aplicar cambios en `.devcontainer/docker-compose.yml` y `workspace-entrypoint.sh`.
2. Actualizar `flow`, `flowctl/stack_ops.py`, `flowctl/tooling.py` y tests.
3. Rebuild/restart del stack workspace (`flow stack ...`) para materializar entrypoint y `user: root`
   de bootstrap.
4. Validar smoke manual: PID 1, `id`, creación de archivo en bind mount, acceso docker.
5. Ejecutar tests focalizados y suite `flowctl`.
6. Revisar y aprobar esta spec (`flow spec review` / `flow spec approve`) antes de tratar el
   contrato como released.

## Rollback

1. Revertir entrypoint, compose, `flow` y `flowctl` a la revisión anterior.
2. Rebuild/restart de servicios `workspace` y `gateway`.
3. Verificar que el stack vuelve a arrancar (aunque reintroduzca archivos root-owned).
4. Mantener tests de ownership en el revert si se desea preservar evidencia de la regresión para
   un reintento posterior.
