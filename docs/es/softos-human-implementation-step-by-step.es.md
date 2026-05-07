# Implementacion de SoftOS paso a paso para humanos

English source: [docs/softos-human-implementation-step-by-step.md](../softos-human-implementation-step-by-step.md)

Source: `docs/softos-human-implementation-step-by-step.md`  
Last updated: 2026-05-07

Esta guia explica como un equipo humano puede implementar y operar SoftOS de punta a punta.

## 1. Definir alcance y repos

1. Identificar el repo raiz del workspace que alojara `flow`, specs y orquestacion.
2. Identificar repos de implementacion (backend, frontend, servicios).
3. Registrar repos target en `workspace.config.json`.

## 2. Bootstrap del workspace

1. Crear el workspace desde el boilerplate SoftOS.
2. Abrir el proyecto en devcontainer.
3. Ejecutar `python3 ./flow init`.
4. Ejecutar `python3 ./flow doctor` y resolver bloqueos.

## 3. Configurar runtime y skills

1. Verificar mapeos de runtime por repo en `workspace.config.json`.
2. Verificar runtime packs en `runtimes/*.runtime.json`.
3. Cargar skills por repo:
   - `python3 ./flow skills context --repo <repo> --json`

## 4. Establecer specs fuente de verdad

1. Crear/curar specs foundation en `specs/000-foundation/**`.
2. Definir specs de dominio en `specs/domains/**`.
3. Definir specs de features en `specs/features/**` con dependencias explicitas.
4. Asegurar que cada feature tenga `targets` claros y plan de validacion.

## 5. Planificar y ejecutar slices

1. Ejecutar plan desde spec:
   - `python3 ./flow plan <spec-id>`
2. Crear/ejecutar slices con write-set acotado.
3. Mantener evidencia en reportes y salidas CI.
4. Evitar tocar superficies fuera de targets declarados.

## 6. Ejecutar gates de CI

1. Gobernanza de specs y contratos:
   - `python3 ./flow ci spec --changed --base <base> --head <head>`
2. Drift y verificacion de contrato:
   - `python3 ./flow drift check --changed --base <base> --head <head> --json`
   - `python3 ./flow contract verify --changed --base <base> --head <head> --json`
3. CI por runtime de repo cuando aplique.

## 7. Operar ciclo de release

1. Hacer cut de release cuando spec y evidencia CI esten completas.
2. Promover release con preflight de staging.
3. Verificar rollout y capturar evidencia.
4. Publicar release notes y tags.

## 8. Gobernanza y observabilidad

1. Usar decision logs para excepciones.
2. Mantener visibles quality gates y politica de riesgo.
3. Mantener docs y specs sincronizados con el comportamiento.
4. Auditar retencion de reportes operativos.

## 9. Documentacion e i18n

1. Ingles es canonico para nuevas docs operativas.
2. Espejo en espanol es requerido para docs operativas/user-facing.
3. Mantener links EN/ES en la parte superior de cada par.
4. Validar con guard i18n en CI.

## 10. Checklist operativo humano

- Workspace levanta limpio en devcontainer.
- `flow doctor` en verde o solo warnings no bloqueantes.
- Grafo de specs explicito y vigente.
- Evidencia CI reproducible.
- Preflight de promote deterministico.
- Publicacion de release trazable.
- Docs y espejos actualizados.
