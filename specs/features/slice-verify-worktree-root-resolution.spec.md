---
schema_version: 3
name: "Fix slice verify worktree root resolution"
description: "Corregir slice verify para inspeccionar el root real del git worktree cuando el repo ya esta checkout directamente en .worktrees/<repo>-<slug>-<slice>, sin concatenar otra vez el path relativo del repo. Agregar prueba para worktree root directo y fallback seguro."
status: approved
owner: platform
single_slice_reason: ""
multi_domain: false
phases: []
depends_on:
  - specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
required_runtimes:
  - python
required_services: []
required_capabilities: []
stack_projects: []
stack_services: []
stack_capabilities: []
targets:
  - ../../flowctl/features.py
  - ../../flowctl/test_slice_verify.py
  - ../../specs/features/slice-verify-worktree-root-resolution.spec.md
---

# Fix slice verify worktree root resolution

## Objetivo

Corregir slice verify para inspeccionar el root real del git worktree cuando el repo ya esta checkout directamente en .worktrees/<repo>-<slug>-<slice>, sin concatenar otra vez el path relativo del repo. Agregar prueba para worktree root directo y fallback seguro.

## Contexto

Contexto inicial capturado desde intake:

- Corregir slice verify para inspeccionar el root real del git worktree cuando el repo ya esta checkout directamente en .worktrees/<repo>-<slug>-<slice>, sin concatenar otra vez el path relativo del repo. Agregar prueba para worktree root directo y fallback seguro.


## Foundations Aplicables

- `specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md`

## Domains Aplicables

- no aplica domain porque es una corrección interna del control plane de SoftOS para `flow slice verify`

## Problema a resolver

`flow slice verify` calcula mal `inspection_path` cuando la slice usa un git worktree cuyo root ya es el repo checkout. En ese caso, concatena de nuevo el path relativo del repo y termina inspeccionando una ruta inexistente como:

- `.worktrees/zsdmsistema-dev-<slug>-<slice>/zsdmsistema-dev`

en lugar de:

- `.worktrees/zsdmsistema-dev-<slug>-<slice>`

Consecuencia:

- fallan referencias `[@test]`
- falla la detección de archivos cambiados
- falla la detección del comando de test
- la verificación de la slice da falsos negativos

## Descripcion inbound

- Corregir slice verify para inspeccionar el root real del git worktree cuando el repo ya esta checkout directamente en .worktrees/<repo>-<slug>-<slice>, sin concatenar otra vez el path relativo del repo. Agregar prueba para worktree root directo y fallback seguro.


## Alcance

### Incluye

- corregir la resolución de `inspection_path` en `flowctl/features.py`
- soportar worktree root directo y mantener fallback seguro cuando el repo sí está anidado
- agregar prueba unitaria para ambos escenarios

### No incluye

- cambios al modelo de planning/worktree path
- cambios a `git worktree add`
- cambios a la semántica de `detect_test_command`

## Repos afectados

| Repo | Targets |
| --- | --- |
| `sdd-workspace-boilerplate` | `../../flowctl/features.py`, `../../flowctl/test_slice_verify.py`, `../../specs/features/slice-verify-worktree-root-resolution.spec.md` |

## Resultado esperado

- `flow slice verify` usa el root real del worktree cuando corresponde
- si existe un layout anidado, sigue usando el path anidado
- la corrección queda fijada con test automatizado

## Reglas de negocio

- nunca asumir que el repo dentro del worktree tiene un subdirectorio adicional con el nombre del repo
- preferir el candidate path anidado solo si existe realmente
- si el candidate path no existe, inspeccionar el root del worktree y reportarlo claramente

## Flujo principal

1. Materializar la slice y resolver `repo_path`, `planned_worktree` y `root`
2. Resolver candidate path `planned_worktree / repo_relative_path`
3. Si ese candidate existe, usarlo
4. Si no existe y el worktree existe, usar `planned_worktree`
5. Verificar con test que no se rompa el escenario anidado

## Contrato funcional

- input clave: `selected["repo_path"]`, `selected["worktree"]`, `root`
- output clave: `inspection_path` correcto para `git_changed_files`, materialización de tests y ejecución de comando de test
- error esperado: si el worktree no existe, seguir inspeccionando `repo_path` como hoy
- side effect: mejora de diagnóstico y reducción de falsos negativos en `slice verify`

## Routing de implementacion

- El repo se deduce desde `targets`.
- Cada slice debe pertenecer a un solo repo.
- El plan operativo vive en `.flow/plans/**`.
- Las dependencias estructurales viven en el frontmatter y deben resolverse antes de aprobar.

## Slice Breakdown

```yaml
- name: slice-verify-root-resolution
  repo: sdd-workspace-boilerplate
  targets:
    - ../../flowctl/features.py
  hot_area: flowctl/slice-verify-logic
  depends_on: []
- name: slice-verify-regression-tests
  repo: sdd-workspace-boilerplate
  targets:
    - ../../flowctl/test_slice_verify.py
    - ../../specs/features/slice-verify-worktree-root-resolution.spec.md
  hot_area: flowctl/slice-verify-tests
  depends_on:
    - slice-verify-root-resolution
```

## Criterios de aceptacion

- si el worktree root ya es el repo checkout, `inspection_path` apunta al root del worktree
- si existe un layout anidado, `inspection_path` sigue apuntando al path anidado
- existe prueba automatizada que cubre ambos escenarios
- `python3 ./flow ci spec specs/features/slice-verify-worktree-root-resolution.spec.md --json` pasa tras la aprobación

## Test plan

- [@test] ../../flowctl/test_slice_verify.py

## Rollout

- aplicar fix en `flowctl/features.py`
- correr tests unitarios del comando
- dejar la spec aprobada y con evidencia de CI de spec

## Rollback

- revertir el cambio en `inspection_path`
- mantener el test para diagnosticar futuras regresiones si se detecta otro modelo de worktree
