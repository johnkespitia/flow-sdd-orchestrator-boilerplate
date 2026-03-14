# SDD Implementation Guide

Guia completa de la implementacion actual de `Spec As Source` y de la orquestacion IA en
`workspace-root`.

## Objetivo

Explicar por que el workspace se implemento de esta forma, que responsabilidades tiene cada capa,
como se usa en la practica, cuales son sus tradeoffs y por que se conservaron los submodulos de
Git como repos de implementacion.

## Resumen ejecutivo

La implementacion actual separa de forma deliberada cuatro cosas:

1. fuente de verdad
2. metodologia SDD
3. estado operativo
4. repos de implementacion

La fuente de verdad vive en el root, en [`specs/`](../specs/README.md).
La metodologia SDD vive en el root, en [`.tessl/`](../.tessl/RULES.md) y
[`tessl.json`](../tessl.json).
El estado operativo vive en [`.flow/`](../.flow/README.md).
El codigo vive en los submodulos [`backend/`](../backend/) y
[`frontend/`](../frontend/).

Esa separacion evita dos fallas comunes:

- prompts y artefactos operativos compitiendo con la spec
- agentes implementando en el repo equivocado o inventando alcance local

## Documentos canonicos

Estos archivos describen el modelo actual y son la referencia principal:

- [README.md](../README.md)
- [AGENTS.md](../AGENTS.md)
- [docs/spec-driven-orchestration.md](./spec-driven-orchestration.md)
- [specs/000-foundation/spec-as-source-operating-model.spec.md](../specs/000-foundation/spec-as-source-operating-model.spec.md)
- [specs/000-foundation/repo-routing-and-worktree-orchestration.spec.md](../specs/000-foundation/repo-routing-and-worktree-orchestration.spec.md)
- [tessl.json](../tessl.json)
- [`.tessl/RULES.md`](../.tessl/RULES.md)
- [`.tessl/tiles/workspace/spec-driven-workspace/index.md`](../.tessl/tiles/workspace/spec-driven-workspace/index.md)
- [flow](../flow)
- [`.flow/README.md`](../.flow/README.md)
- [backend/AGENTS.md](../backend/AGENTS.md)
- [frontend/AGENTS.md](../frontend/AGENTS.md)

## Problema que resuelve esta arquitectura

Antes de esta implementacion era facil caer en uno o varios de estos problemas:

- especificaciones dispersas entre root y submodulos
- prompts manuales que funcionaban una vez, pero no eran reproducibles
- artefactos de planeacion convertidos accidentalmente en fuente de verdad
- agentes trabajando directo sobre codigo sin una spec aprobada
- confusion sobre que repo debia recibir un cambio
- dificultad para que el equipo replique el flujo solo abriendo el devcontainer

La implementacion actual existe para cerrar esas fugas de forma estructural, no procedural.

## Principios de la implementacion

### 1. `specs/**` es la fuente de verdad

La decision principal es que la verdad funcional y arquitectonica vive en el root:

- [`specs/000-foundation/`](../specs/000-foundation/)
- [`specs/domains/`](../specs/domains/)
- [`specs/features/`](../specs/features/)

Justificacion:

- el producto no pertenece a un solo repo
- muchas features afectan mas de una aplicacion
- una sola spec del root puede describir alcance, routing y pruebas esperadas
- la orquestacion no necesita reinterpretar el problema desde cada submodulo

### 2. Tessl disciplina el SDD, no la ejecucion

La metodologia vive en el root:

- [`tessl.json`](../tessl.json)
- [`.tessl/RULES.md`](../.tessl/RULES.md)
- [`.tessl/tiles/workspace/spec-driven-workspace/index.md`](../.tessl/tiles/workspace/spec-driven-workspace/index.md)

Justificacion:

- la metodologia debe ser compartida por todo el workspace
- si Tessl vive en cada submodulo, reaparece la duplicacion de flujo y de reglas
- el equipo puede clonar el repo y tener el mismo punto de entrada metodologico

### 3. `.flow/**` guarda estado operativo, no requerimientos

El estado del SDLC se separa de la spec:

- [`.flow/state/`](../.flow/state/)
- [`.flow/plans/`](../.flow/plans/)
- [`.flow/reports/`](../.flow/reports/)
- [`.flow/runs/`](../.flow/runs/)

Justificacion:

- planning, handoffs y reportes cambian mucho mas rapido que la spec
- el estado operativo debe ser descartable y re-generable
- mantenerlo fuera de `specs/**` evita que se vuelva pseudo-canonico
- el contenido generado en `state/`, `plans/` y `reports/` se ignora por Git; solo quedan
  placeholders versionados

### 4. `flow` es la capa de control

El CLI [`flow`](../flow) orquesta el SDLC del workspace.

Responsabilidades:

- validar el scaffold del workspace
- crear specs canonicas
- generar revision de spec con findings reales
- aprobar specs solo cuando no quedan placeholders ni `targets` invalidos
- generar planes por repo o slice
- preparar handoffs de slice
- verificar slices con checks estructurales sobre spec, `targets`, `[@test]` y diff observado
- registrar estado operativo

Justificacion:

- el equipo no debe depender de recordar prompts complejos
- un CLI pequeno y versionado es mas reproducible que una cadena de instrucciones manuales
- `flow` no reemplaza Tessl; lo encadena con estado operativo explicito
- `flow` tambien resuelve el contexto correcto del devcontainer, por lo que Docker/Tessl/BMAD no
  dependen de que cada cliente recuerde nombres de proyecto o comandos locales

### 4.1 `flow` como control plane real

La primera implementacion busca que `flow` sea el punto de entrada unico del workspace:

- `flow stack ...` para administrar Docker y el devcontainer
- `flow tessl ...` para ejecutar Tessl en el entorno canonico
- `flow bmad ...` para ejecutar BMAD desde el mismo control plane y bootstrappear `_bmad/`
- `flow spec|plan|slice|status` para el SDLC spec-driven

`make` queda como capa de conveniencia para humanos, no como otra fuente de verdad operativa.

### 5. Los submodulos son repos de implementacion

Los submodulos no son la fuente de verdad funcional del sistema. Son repos de codigo y de
artefactos tecnicos locales.

Reglas activas:

- [backend/AGENTS.md](../backend/AGENTS.md)
- [frontend/AGENTS.md](../frontend/AGENTS.md)

Justificacion:

- el trabajo real de backend y frontend sigue teniendo historiales separados
- despliegue, ownership y herramientas de cada stack siguen siendo independientes
- los agentes implementan en el repo correcto despues de leer la spec del root

Nota importante:

Algunos submodulos todavia pueden contener artefactos tecnicos locales o transicionales. Por
ejemplo, hoy `backend` aun conserva referencias utiles para migracion:

- [backend/specs/features/wave-1-identity-bootstrap.spec.md](../backend/specs/features/wave-1-identity-bootstrap.spec.md)
- [backend/specs/000-foundation/database-migration-strategy.spec.md](../backend/specs/000-foundation/database-migration-strategy.spec.md)
- [backend/specs/000-foundation/legacy-to-v2-integration.spec.md](../backend/specs/000-foundation/legacy-to-v2-integration.spec.md)
- [backend/specs/000-foundation/shared-database-migration.spec.md](../backend/specs/000-foundation/shared-database-migration.spec.md)
- [backend/docs/legacy-db/schema-snapshot-2026-03-12.md](../backend/docs/legacy-db/schema-snapshot-2026-03-12.md)

Esos documentos pueden servir como referencia local o material de migracion, pero no deben competir
con `specs/**` del root como fuente de verdad del SDLC del sistema.

## Arquitectura de capas

| Capa | Ubicacion | Responsabilidad |
| --- | --- | --- |
| Fuente de verdad | `specs/**` | comportamiento, restricciones, alcance, criterios de aceptacion |
| Metodologia SDD | `.tessl/**`, `tessl.json` | requirement gathering, reglas de estilo, verificacion |
| Orquestacion | `flow` | plan, slices, handoffs, routing y estado |
| Estado operativo | `.flow/**` | estados, planes, reportes y artefactos efimeros |
| Codigo | `backend/`, `frontend/` | implementacion, tests y runtime |

## Flujo SDLC resultante

El SDLC quedo modelado asi:

1. idea
2. `spec create`
3. `spec review`
4. `spec approve`
5. `plan`
6. `slice start`
7. implementacion en el submodulo correspondiente
8. `slice verify`
9. merge por repo
10. actualizacion del puntero del submodulo en el root

Los estados vigentes estan definidos en
[spec-as-source-operating-model.spec.md](../specs/000-foundation/spec-as-source-operating-model.spec.md).

## Routing por `targets`

La implementacion no usa una tabla manual fija para decidir el repo.
Usa los `targets` de la spec y falla cerrado si aparece un root no permitido.

Ejemplos:

- `../../backend/app/**` -> `backend`
- `../../backend/tests/**` -> `backend`
- `../../frontend/src/**` -> `frontend`
- `../../.devcontainer/**` -> `workspace-root`

Justificacion:

- la spec ya sabe que archivos describe
- el routing se vuelve explicito y auditable
- el agente no necesita "adivinar" ownership
- un typo en el root de un `target` no termina planeado por error en otro repo

## Justificacion tecnica de los submodulos de Git

La decision de mantener submodulos fue deliberada.

### Por que no convertirlo todo en un solo repo plano

Porque backend y frontend siguen teniendo:

- ciclos de cambio distintos
- historiales distintos
- herramientas distintas
- necesidades de despliegue distintas
- ownership potencialmente distinto

Unificar el codigo no arregla la coordinacion del SDD; solo cambia donde vive el problema.

### Beneficios tecnicos concretos de usar submodulos aqui

1. Historial independiente por aplicacion.
   Backend y frontend pueden conservar trazabilidad tecnica y de revisiones sin mezclar commits.

2. Integracion controlada desde el root.
   El root fija una combinacion exacta de SHAs de backend y frontend, lo que da un snapshot del
   sistema completo.

3. Merges por dominio tecnico.
   El cambio de codigo se revisa dentro del repo correspondiente, no mezclado con artefactos del
   sistema.

4. Worktrees mas limpios.
   Cada slice puede salir desde el submodulo correcto, con ramas y worktrees acotados al repo que
   realmente cambia.

5. Menor acoplamiento entre runtime y source-of-truth.
   El root coordina y documenta; los submodulos implementan y prueban.

### Costos tecnicos reales de usar submodulos

- hay que hacer merge primero en el submodulo y luego actualizar el puntero del root
- es facil quedar en detached HEAD si no se entiende bien Git submodules
- el onboarding exige disciplina para saber en que repo se esta trabajando
- CI y automatizacion deben contemplar tanto el root como los submodulos

### Por que aun asi conviene

Porque en este diseño el root ya actua como "control plane" del producto. Los submodulos quedan
como "data plane" de implementacion. Esa separacion encaja mucho mejor con Git submodules que con
un modelo donde cada repo trata de definir sus propias specs canonicas.

## Comandos recomendados

### Regla general

Documentamos `python3 ./flow` como comando canonico porque funciona de forma consistente tanto en
host como dentro del devcontainer. `./flow` tambien puede funcionar, pero `python3 ./flow` evita
depender del bit ejecutable o del shell activo.

### Bootstrap del entorno

```bash
make init
make up
make sh
```

### Validacion del scaffold

```bash
make flow-doctor
python3 ./flow stack doctor
python3 ./flow doctor
python3 ./flow status
```

### Crear una feature

```bash
python3 ./flow spec create identity-bootstrap --title "Identity Bootstrap" --repo backend
python3 ./flow spec review identity-bootstrap
python3 ./flow spec approve identity-bootstrap
python3 ./flow plan identity-bootstrap
python3 ./flow status identity-bootstrap
```

### Preparar slices

```bash
python3 ./flow slice start identity-bootstrap backend-main
python3 ./flow slice verify identity-bootstrap backend-main
```

`slice verify` ya no es solo una plantilla. Hoy valida:

- que la spec siga aprobada
- que los `targets` se enruten al repo correcto
- que la slice no contenga ownership cruzado
- que `[@test]` resuelva a rutas reales
- que el diff observado permanezca dentro de `targets` y tests declarados
- y, cuando detecta un runner compatible, intenta ejecutar los tests enlazados

### Wrapper por Make

```bash
make stack ARGS='ps'
make tessl ARGS='whoami'
make flow ARGS='spec create identity-bootstrap --title "Identity Bootstrap" --repo backend'
make flow-status
```

`make` no implementa logica propia del stack ni de Tessl. Solo delega en `flow`.

### Tessl y BMAD

```bash
python3 ./flow tessl -- --help
python3 ./flow tessl -- whoami
python3 ./flow bmad -- --help
python3 ./flow bmad -- status
python3 ./flow bmad -- install --tools none --yes
```

Notas:

- `flow tessl` usa el binario local si ya estas dentro del `workspace`; desde host lo enruta al
  contenedor correcto.
- `flow bmad` resuelve `bmad`, `bmad-method` o `npx bmad-method` y siempre ejecuta desde
  `/workspace`.
- si BMAD requiere otro ejecutable, se puede ajustar con `PLG_BMAD_COMMAND`.
- la imagen del devcontainer incluye BMAD CLI; el comando `install` crea el proyecto local en
  `_bmad/`.
- `_bmad/` es parte versionable del workspace; `_bmad-output/` debe tratarse como artefacto local.

### Worktrees

`flow slice start` prepara el handoff y te devuelve el comando Git correspondiente.
Por defecto, `flow` crea worktrees bajo `.worktrees/` dentro del propio workspace.

Justificacion:

- la ruta existe igual desde el host y desde `/workspace` en el devcontainer
- evita mezclar rutas del host con rutas internas del contenedor
- mantiene el estado multiagente junto al superproject y fuera de los submodulos

Si hiciera falta otra topologia, se puede sobreescribir con `PLG_WORKTREE_ROOT`.

Ejemplo esperado dentro del devcontainer:

```bash
git -C /workspace/backend worktree add /workspace/.worktrees/backend-identity-bootstrap-backend-main -b feat/identity-bootstrap-backend-main
```

Ejemplo esperado desde el host:

```bash
git -C "$(pwd)/backend" worktree add "$(pwd)/.worktrees/backend-identity-bootstrap-backend-main" -b feat/identity-bootstrap-backend-main
```

### Orden correcto de merge

1. mergear la rama del submodulo
2. verificar tests y drift
3. actualizar el puntero del submodulo en `workspace-root`
4. mergear el root

Ese orden no es accidental. Es una consecuencia directa de haber separado fuente de verdad del
sistema y repos de implementacion.

## Justificaciones de diseño

### Por que el root concentra `specs/**`

- porque el producto es transversal a backend y frontend
- porque las features cross-repo necesitan una sola narrativa canónica
- porque evita specs duplicadas o divergentes
- porque centraliza los gates humanos del SDLC

### Por que el root concentra `.tessl/**`

- porque la metodologia debe ser consistente para todo el equipo
- porque los tiles deben vivir cerca de la fuente de verdad
- porque si se distribuyen en submodulos reaparece la duplicacion metodologica

### Por que el root concentra `.flow/**`

- porque el estado del SDLC es del sistema, no de un solo repo
- porque el planner y el orchestrator necesitan ver todo el workspace
- porque los handoffs multi-repo deben ser reconciliables en un solo lugar

### Por que los submodulos no deben tener specs canonicas paralelas

- porque rompe `Spec As Source`
- porque genera conflictos de ownership
- porque vuelve ambiguo cual documento manda
- porque obliga a sincronizacion manual entre specs hermanas

Esto no significa que un submodulo no pueda tener documentacion tecnica local, snapshots legacy o
specs transicionales de implementacion. Significa que esos artefactos no mandan sobre la spec del
root cuando el tema pertenece al sistema, al routing o al SDLC global.

## Tradeoffs

### Ventajas

- una sola fuente de verdad del sistema
- un solo control plane operativo del workspace
- routing explicito y verificable por `targets`
- onboarding mas simple para el equipo
- metodologia y tooling reproducibles desde el devcontainer
- mejor acoplamiento entre specs, slices y handoffs
- worktrees por repo sin perder coordinacion global
- artifacts operativos locales sin ensuciar Git

### Costos

- el root se vuelve mas importante y requiere disciplina editorial
- los submodulos pierden autonomia para definir requerimientos canónicos
- los merges son en dos pasos: submodulo y luego root
- algunos detalles muy locales de implementacion requieren subir primero a la spec del root
- el CLI `flow` hoy no automatiza merge ni release de forma end-to-end
- BMAD agrega bootstrap propio en `_bmad/`, asi que introduce artefactos adicionales cuando se activa

### Tradeoff principal

La implementacion favorece consistencia global por encima de autonomia local. Es una decision
correcta cuando lo prioritario es un SDLC reproducible y auditable para equipos y agentes.

## Alternativas consideradas y por que no se usaron

### 1. Specs locales por submodulo

No se uso porque:

- duplicaba la fuente de verdad
- complicaba features cross-repo
- obligaba a reconciliacion manual entre documentos

### 2. Orquestacion basada solo en prompts

No se uso porque:

- no es reproducible
- no deja estado operativo estructurado
- escala mal cuando entra mas de un agente o mas de un dev

### 3. BMAD o un orquestador pesado como centro del sistema

No se uso como columna vertebral principal porque:

- la orquestacion no debe competir con la spec
- primero debia cerrarse el contrato de source-of-truth
- el workspace necesitaba una capa de control simple y versionada

## Limitaciones actuales

- `flow` todavia no automatiza merge ni release de forma end-to-end
- `.flow/**` usa archivos simples, no una maquina de estados transaccional
- la ejecucion real de slices sigue requiriendo intervencion humana
- el workflow asume que el equipo entiende Git submodules y worktrees

Estas limitaciones son aceptables para una v1 porque mantienen el sistema simple y auditable.

## Recomendaciones operativas

1. Abrir siempre el workspace en el devcontainer.
2. Leer primero la spec del root y luego el `AGENTS.md` del submodulo.
3. Usar `python3 ./flow` como comando base.
4. No crear specs locales paralelas en backend o frontend.
5. No mergear el root antes de mergear el submodulo correspondiente.
6. Mantener `targets` y `[@test]` alineados en el mismo cambio.

## Conclusion

La implementacion actual no intenta convertir a Tessl, `flow`, Git submodules y los agentes en la
misma cosa. Hace lo contrario: les da fronteras claras.

- Tessl define la disciplina del SDD.
- `specs/**` define la verdad.
- `flow` coordina el SDLC.
- `flow` opera como control plane del stack y de los adapters.
- `.flow/**` conserva el estado operativo.
- los submodulos implementan codigo y tests.

Esa separacion es precisamente lo que hace que la implementacion sea reproducible para el equipo,
compatible con agentes y adecuada para evolucionar hacia una orquestacion IA mas automatizada sin
romper `Spec As Source`.

## Boilerplate

Si. Esta primera implementacion ya puede servir como boilerplate para otros proyectos SDD, con tres
adaptaciones:

1. reemplazar `backend` y `frontend` por los repos reales del sistema
2. ajustar `DEFAULT_TARGETS`, `TARGET_ROOTS`, `PLG_WORKSPACE_PATH` y `PLG_BMAD_COMMAND` en [`flow`](../flow)
3. versionar `specs/**`, `.tessl/**`, `.flow/README.md`, `Makefile` y la carpeta `.devcontainer/`

La idea reusable no es el dominio PLG. Es la separacion:

- `specs/**` como source of truth
- `flow` como control plane
- `make` como fachada humana
- subrepos como implementacion
- Tessl y BMAD como adapters del workspace, no como centro del sistema
