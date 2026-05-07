# SoftOS Harness Core y Profiles

English source: [docs/harness-core-and-profiles.md](../harness-core-and-profiles.md)

Source: `docs/harness-core-and-profiles.md`  
Last updated: 2026-05-07

Este paquete separa la politica reutilizable de Harness Core de los perfiles
especificos de cada proyecto.

## Novedades

- Policy pack reutilizable en `policies/harness-core/*`.
- Contrato de perfil de proyecto en `profiles/<profile-id>/profile.json`.
- Ejemplo seguro para open source en
  `profiles/example-api-ticket/profile.json`.
- Validador solo con stdlib en `scripts/harness/validate_profile.py`.
- Spec fuente de la feature en
  `specs/features/softos-harness-core-and-profiles.spec.md`.

## Por que

Las practicas de delivery suelen mezclar controles universales con convenciones
locales como labels de repositorio, comandos de deploy, runners de E2E,
sistemas de tickets y herramientas de comunicacion. Esta separacion mantiene la
politica reutilizable segura para open source y permite que cada proyecto adapte
el core a su flujo.

## Core vs profile

| Capa | Define | Ejemplo |
| --- | --- | --- |
| Core | lifecycle, gates, contratos de revision, evidencia, progreso, conceptos de PR readiness | R1-R5, open questions vacias, dry-run first |
| Profile | herramientas locales, convenciones del repo, labels, comandos de deploy/E2E, formato mirror, canales de comunicacion | labels de repositorio, comando de staging, runner E2E |

## Perfiles incluidos

- `profiles/example-api-ticket/profile.json` - perfil de ejemplo seguro para open source.

Los proyectos deberian crear perfiles privados para repositorios especificos,
labels, sistemas de tickets, comandos de deploy, canales de comunicacion y
runners de validacion.


## Usage and Cost Harness

El Harness Core incluye una politica de telemetria de uso/costo en
`policies/harness-core/usage-and-cost.md`. Los profiles pueden activar
`usage_telemetry` para emitir checkpoints en progress updates y resumen final,
marcando cada valor como `exact`, `provider_reconciled` o `estimated`.

## Validacion

```bash
python3 scripts/harness/validate_profile.py --root . --json
```

El validador garantiza:

- existen los archivos requeridos del core
- el core no filtra terminos privados obvios
- los perfiles extienden `policies/harness-core`
- se declaran los gates R1-R5
- existen label discovery, communication ledger y dry-run-first automation

## Ruta de adopcion

1. Copia o versiona las politicas core.
2. Usa `profiles/example-api-ticket/profile.json` como plantilla.
3. Mantén datos privados del perfil fuera del control de codigo publico cuando aplique.
4. Ejecuta el validador en CI o antes de publicar cambios de perfil.
