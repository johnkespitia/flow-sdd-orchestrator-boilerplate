# Spec-Driven Workspace

Este tile define el flujo base de `Spec As Source` para el workspace root.

## Requirement Gathering

Ante una nueva iniciativa:

1. revisar `specs/000-foundation/**`
2. revisar `specs/domains/**` si aplica
3. crear o actualizar una spec en `specs/features/**`
4. cerrar ambiguedades antes de implementar
5. aprobar la spec antes de crear slices

## Routing

Los repos de implementacion se deducen desde `targets` y la configuracion del workspace.

- `../../<repo>/...` -> el repo configurado correspondiente
- `../../.devcontainer/**` o archivos del root -> el root repo del workspace

## Verification

- mantener `targets` alineados
- enlazar tests con `[@test]`
- revisar drift entre spec, codigo y tests

Lee tambien:

- [Spec Format](./spec-format.md)
- [Spec Styleguide](./spec-styleguide.md)
- [Spec Verification](./spec-verification.md)
