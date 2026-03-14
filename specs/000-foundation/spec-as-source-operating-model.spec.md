---
name: Spec As Source Operating Model
description: Contrato operativo del workspace para usar specs del root como fuente de verdad del SDLC
status: approved
owner: platform
targets:
  - ../../tessl.json
  - ../../.tessl/**
  - ../../flow
  - ../../AGENTS.md
  - ../../README.md
  - ../../docs/spec-driven-orchestration.md
  - ../../specs/**/*.spec.md
---

# Spec As Source Operating Model

## Objetivo

Definir el modelo operativo del workspace para que `specs/**` sea la fuente de verdad del
producto, de la arquitectura y del trabajo agentico.

## Regla principal

- Ningun agente implementa codigo sin una spec aprobada.
- Ningun artefacto en `.flow/**` reemplaza una spec.
- Los cambios de comportamiento deben actualizar la spec en el mismo cambio.

## Canonicalidad

La fuente de verdad canónica del workspace vive en:

- `specs/000-foundation/**`
- `specs/domains/**`
- `specs/features/**`

La salida operativa vive en:

- `.flow/state/**`
- `.flow/plans/**`
- `.flow/reports/**`
- `.flow/runs/**`

## Estado operativo

Cada feature pasa por estos estados:

| Estado | Significado |
| --- | --- |
| `idea` | Aun no existe spec |
| `draft-spec` | La spec esta en elaboracion |
| `reviewing-spec` | La spec esta siendo revisada |
| `approved-spec` | La spec puede pasar a planning |
| `planned` | Existe plan de slices |
| `slice-ready` | Hay slices listas para ejecutarse |
| `implementing` | Una slice esta en curso |
| `in-review` | La slice esta en revision tecnica |
| `in-qa` | La slice esta en verificacion |
| `merged` | La slice o feature ya fue mergeada |
| `released` | La feature ya cerro su SDLC |

## Gates humanos

Los unicos gates manuales obligatorios son:

1. `spec-approved`
2. `plan-approved`
3. `merge-approved`

## Contrato de trazabilidad

- Toda spec debe tener `targets`.
- Toda spec implementada debe enlazar tests relevantes con `[@test]`.
- Los reviewers deben contrastar spec, codigo y tests antes de aprobar.

## Contrato de orquestacion

- El root coordina el SDLC.
- Los submodulos contienen implementaciones de codigo.
- Los agentes deben enrutar el trabajo leyendo primero `targets`.
