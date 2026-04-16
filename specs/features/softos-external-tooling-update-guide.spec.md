---
schema_version: 3
name: "SoftOS external tooling update guide"
description: "Documentar y preparar el entorno para actualizar BMAD, Tessl, Engram y skills externos con defaults latest y opcion de pin reproducible."
status: approved
owner: platform
single_slice_reason: "documentation plus devcontainer version args are one bounded toolchain governance surface"
multi_domain: false
phases: []
depends_on:
  - specs/000-foundation/spec-as-source-operating-model.spec.md
  - specs/000-foundation/spec-driven-delivery-and-infrastructure.spec.md
required_runtimes: []
required_services: []
required_capabilities:
  - agent-memory-engram
stack_projects: []
stack_services: []
stack_capabilities: []
targets:
  - ../../.devcontainer/Dockerfile
  - ../../flow
  - ../../flowctl/stack.py
  - ../../flowctl/test_stack_compose_files.py
  - ../../docs/external-tooling-updates.md
  - ../../docs/softos-agent-dev-handbook.md
  - ../../README.md
  - ../../specs/features/softos-external-tooling-update-guide.spec.md
---

# SoftOS external tooling update guide

## Objetivo

Explicar como actualizar herramientas externas de SoftOS y preparar el entorno para que el devcontainer pueda instalar la ultima version de BMAD, Tessl, Engram y pnpm por defecto, sin perder la capacidad de pinnear versiones reproducibles.

## Contexto

SoftOS usa herramientas externas en tres planos distintos:

- binarios instalados en el devcontainer `workspace`
- assets versionados del workspace como `_bmad/**`, `.tessl/**`, `.agents/skills/**` y `workspace.skills.json`
- estado operativo local como `.flow/memory/engram`, `.flow/reports/**` y `.flow/state/**`

Antes de esta spec, el Dockerfile ya tomaba versions actuales para npm packages y latest release para Engram, pero no exponia un contrato explicito de version args ni un manual operativo central.

## Governing Decision

- El modo default de desarrollo debe seguir latest en rebuild.
- El mismo Dockerfile debe permitir pinning por build args.
- El manual debe separar binarios, assets versionados y estado operativo.
- Engram memory sigue siendo consultiva y no puede ser fuente de verdad.
- Actualizar `_bmad/**` o `.tessl/**` es cambio versionado y requiere revision normal de diff.

## Executable Surface Inventory

| Superficie | Cambio obligatorio | Prohibido |
|---|---|---|
| `.devcontainer/Dockerfile` | Agregar ARGs de version con default `latest` para pnpm, Tessl, BMAD y Engram. | Romper instalacion default del devcontainer. |
| `flowctl/stack.py` | Resolver Compose dinamicamente: preferir `docker compose` y caer a `docker-compose`. | Hardcodear un runtime Compose unico. |
| `flow` | Permitir stack context si existe `docker-compose` aunque falte plugin `docker compose`. | Cambiar contratos de comandos `stack`. |
| `flowctl/test_stack_compose_files.py` | Cubrir render de comandos y fallback standalone. | Depender del Docker real del host en unit tests. |
| `docs/external-tooling-updates.md` | Documentar update/latest/pinning/validacion por herramienta. | Mezclar memoria local con source-of-truth versionado. |
| `docs/softos-agent-dev-handbook.md` | Enlazar el manual desde el handbook operativo. | Duplicar todo el manual. |
| `README.md` | Exponer el manual para nuevos usuarios del workspace. | Prometer reproducibilidad cuando se usa `latest`. |
| Spec | Declarar targets y evidencia. | Incluir targets fuera de la superficie del cambio. |

## Algorithm

1. Definir ARGs:
   - `PNPM_VERSION=latest`
   - `TESSL_CLI_VERSION=latest`
   - `BMAD_METHOD_VERSION=latest`
   - `ENGRAM_VERSION=latest`
2. Instalar npm packages usando `package@${VERSION}`.
3. Resolver Engram desde `/releases/latest` cuando `ENGRAM_VERSION=latest`.
4. Resolver Engram desde `/releases/tags/<tag>` cuando `ENGRAM_VERSION` tenga un tag explicito.
5. Documentar que `latest` requiere rebuild sin cache para evitar capas Docker reutilizadas.
6. Documentar comandos de doctor/smoke para validar el resultado.
7. Resolver el runtime Compose en el control plane:
   - si `docker compose version` retorna cero, usar `docker compose`
   - si no, y existe `docker-compose`, usar `docker-compose`
   - si ninguno existe, bloquear con mensaje accionable

## Stop Conditions

- No cambiar estado de memoria `.flow/memory/engram`.
- No ejecutar actualizaciones destructivas de `_bmad/**` ni `.tessl/**` en esta spec.
- No pinnear versiones concretas sin que el usuario lo pida.
- No declarar validado el rebuild real si no se ejecuta por red/tiempo.
- No romper hosts que ya tienen Docker Compose plugin.

## Slice Breakdown

```yaml
- name: external-tooling-update-guide
  targets:
    - ../../.devcontainer/Dockerfile
    - ../../flow
    - ../../flowctl/stack.py
    - ../../flowctl/test_stack_compose_files.py
    - ../../docs/external-tooling-updates.md
    - ../../docs/softos-agent-dev-handbook.md
    - ../../README.md
    - ../../specs/features/softos-external-tooling-update-guide.spec.md
  hot_area: workspace toolchain
  depends_on: []
  slice_mode: governance
  surface_policy: required
  minimum_valid_completion: devcontainer exposes latest/pinned version args and docs explain update flow
  validated_noop_allowed: false
  acceptable_evidence:
    - python3 ./flow ci spec specs/features/softos-external-tooling-update-guide.spec.md
    - python3 ./flow spec review specs/features/softos-external-tooling-update-guide.spec.md
    - python3 -m unittest flowctl.test_stack_compose_files
    - PYTHONPYCACHEPREFIX=/tmp/softos-pycache python3 -m py_compile flow flowctl/parser.py flowctl/skills_ops.py flowctl/memory_ops.py flowctl/tooling.py
    - git diff --check
```

## Verification Matrix

```yaml
- name: spec-ci
  level: custom
  command: python3 ./flow ci spec specs/features/softos-external-tooling-update-guide.spec.md
  blocking_on:
    - ci
  environments:
    - local
  notes: valida estructura, targets y dependencias de la spec

- name: spec-review
  level: custom
  command: python3 ./flow spec review specs/features/softos-external-tooling-update-guide.spec.md
  blocking_on:
    - approval
  environments:
    - local
  notes: valida que la spec sea ejecutable y no derive de scope

- name: python-compile
  level: custom
  command: PYTHONPYCACHEPREFIX=/tmp/softos-pycache python3 -m py_compile flow flowctl/parser.py flowctl/skills_ops.py flowctl/memory_ops.py flowctl/tooling.py
  blocking_on:
    - ci
  environments:
    - local
  notes: asegura que no se rompio superficie Python relacionada

- name: stack-compose-command-tests
  level: custom
  command: python3 -m unittest flowctl.test_stack_compose_files
  blocking_on:
    - ci
  environments:
    - local
  notes: valida render de docker compose plugin y fallback docker-compose standalone

- name: diff-check
  level: custom
  command: git diff --check
  blocking_on:
    - ci
  environments:
    - local
  notes: detecta whitespace invalido
```

## Acceptance Criteria

- El Dockerfile permite latest por defecto para pnpm, Tessl, BMAD y Engram.
- El Dockerfile permite pinning por build args sin editar el archivo.
- El manual explica update latest, pinning, validacion y separacion entre binarios/assets/estado.
- El manual incluye comandos para BMAD, Tessl, Engram y skills.
- `flow stack build` funciona en hosts con `docker-compose` standalone aunque falte plugin `docker compose`.
- README y handbook apuntan al manual.
