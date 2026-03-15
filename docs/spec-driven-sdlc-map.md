# Spec-Driven SDLC Map

Mapa operativo del flujo completo de desarrollo, CI y CD para este workspace.

## Objetivo

Dejar en una sola referencia:

- el orden correcto del SDLC
- los estados esperados de una feature
- los comandos `flow` que mueven cada etapa
- los gates humanos y automáticos
- y el punto exacto donde entran CI, release e infraestructura

## Alcance

Este documento describe el flujo operativo vigente del workspace:

- lo que ya existe en `flow`
- los workflows GitHub Actions que lo ejecutan
- y los siguientes pasos razonables para endurecer el delivery

## Principio rector

La spec del root gobierna todo el flujo:

1. qué comportamiento se quiere
2. qué repos están afectados
3. qué tests deben existir
4. qué artefactos se publican
5. qué entornos se pueden promover
6. qué infraestructura cambia

El flujo no es:

- escribir código
- abrir PR
- ver si pasa
- desplegar algo

El flujo correcto es:

- aprobar spec
- planear slices
- implementar dentro de `targets`
- validar drift entre spec, código y tests
- promover un snapshot completo del sistema

## Mapa de estados

Los estados canónicos actuales de una feature son:

| Estado | Significado | Gate de salida |
| --- | --- | --- |
| `idea` | Aún no existe spec | creación de spec |
| `draft-spec` | La spec existe pero no está cerrada | review de spec |
| `reviewing-spec` | La spec está en revisión | aprobación humana |
| `approved-spec` | La spec puede pasar a planning | `plan-approved` |
| `planned` | Existe plan por slices/repos | slices listas |
| `slice-ready` | La feature tiene slices ejecutables | arranque de slice |
| `implementing` | Hay implementación en curso | verify + PR |
| `in-review` | La slice pasó a revisión técnica | CI + review |
| `in-qa` | La slice o feature está en verificación | merge-approved |
| `merged` | La implementación quedó integrada | release cut |
| `released` | La feature fue promovida al entorno objetivo | cierre del SDLC |

## Flujo completo

```text
idea
  -> spec create
draft-spec
  -> spec review
reviewing-spec
  -> spec approve
approved-spec
  -> plan
planned
  -> slice start
slice-ready
  -> implementación en submódulo
implementing
  -> slice verify
in-review
  -> PR + CI
in-qa
  -> merge submódulo
merged
  -> merge root + release cut + promote
released
```

## Flujo operativo por etapas

### 1. Crear y cerrar la spec

Comandos actuales:

```bash
python3 ./flow spec create identity-bootstrap --title "Identity Bootstrap" --repo backend --repo frontend
python3 ./flow spec review identity-bootstrap
python3 ./flow spec approve identity-bootstrap
```

Salida esperada:

- spec en `specs/features/identity-bootstrap.spec.md`
- findings de review en `.flow/reports/**`
- estado `approved-spec`

Gate:

- humano: la spec debe quedar aprobada

### 2. Planear la feature

Comando actual:

```bash
python3 ./flow plan identity-bootstrap
```

Salida esperada:

- plan por slices en `.flow/plans/identity-bootstrap.json`
- estado `planned`

Gate:

- humano: confirmar que los slices son correctos

### 3. Arrancar una slice

Comando actual:

```bash
python3 ./flow slice start identity-bootstrap backend-main
```

Salida esperada:

- handoff operativo para esa slice
- estado `implementing`
- repo y ownership resueltos desde `targets`

Regla:

- la implementación ocurre dentro del submódulo correcto
- no se debe salir de `targets`

### 4. Implementar código y tests

Trabajo esperado:

- cambios en el submódulo afectado
- tests enlazados por `[@test]`
- cero drift intencional entre spec, código y tests

Comando actual al cerrar la slice:

```bash
python3 ./flow slice verify identity-bootstrap backend-main
```

Salida esperada:

- revisión estructural sobre `targets`, `[@test]`, ownership y diff observado
- intento de ejecución de tests enlazados si el runner es detectable
- estado `in-review`

### 5. Pull Request y CI

Esta etapa queda dividida en dos tipos de CI.

### 5.1 CI del submódulo

Responsabilidad:

- lint
- unit tests
- build
- publicación opcional de artefacto por SHA

Repos:

- `backend`
- `frontend`

Estado deseado:

- el PR del submódulo solo certifica la implementación local
- hoy existen workflows mínimos en `backend/.github/workflows/backend-ci.yml` y
  `frontend/.github/workflows/frontend-ci.yml`

### 5.2 CI del root

Responsabilidad:

- validar que la feature siga alineada con la spec
- verificar `targets`
- verificar `[@test]`
- verificar drift entre spec y diff
- correr smoke tests cross-repo cuando aplique

Comandos actuales:

```bash
python3 ./flow ci spec --changed --base <sha> --head <sha>
python3 ./flow ci repo backend --base <sha> --head <sha>
python3 ./flow ci repo frontend --base <sha> --head <sha>
python3 ./flow ci integration --profile smoke
```

Estado deseado:

- solo pasa a merge cuando la implementación local y la coherencia global pasen a la vez

### 6. Merge técnico

Orden correcto:

1. merge del submódulo
2. actualización del puntero del submódulo en el root
3. merge del root

Razón:

- el submódulo produce el artefacto técnico
- el root fija el snapshot exacto del sistema

Este orden no es opcional en un workspace con submódulos.

### 7. Release cut

Aquí empieza CD real.

Comandos actuales:

```bash
python3 ./flow release cut --version 2026.03.14-1 --spec identity-bootstrap
python3 ./flow release manifest --version 2026.03.14-1
python3 ./flow release status --version 2026.03.14-1
```

Salida esperada:

- manifest de release con:
  - SHA del root
  - SHA de cada submódulo
  - specs incluidas
  - evidencia de CI
  - artefactos o imágenes con digest
  - entorno y timestamps

Ejemplo lógico de manifest:

```json
{
  "version": "2026.03.14-1",
  "root_sha": "abc123",
  "repos": {
    "backend": "def456",
    "frontend": "ghi789"
  },
  "specs": [
    "specs/features/identity-bootstrap.spec.md"
  ],
  "evidence": {
    "root_ci": "passed",
    "backend_ci": "passed",
    "frontend_ci": "passed"
  }
}
```

### 8. Promoción a entornos

Comandos actuales:

```bash
python3 ./flow release promote --version 2026.03.14-1 --env preview
python3 ./flow release promote --version 2026.03.14-1 --env staging --approver "release-manager"
python3 ./flow release promote --version 2026.03.14-1 --env production --approver "release-manager"
```

Regla recomendada:

- `preview`: automático
- `staging`: aprobación humana
- `production`: aprobación humana fuerte

En este punto la unidad de promoción no es un repo suelto.  
Es el snapshot completo definido por el root.

### 9. Infraestructura gobernada por spec

Si la feature toca infraestructura, la infraestructura entra como otro proyecto enrutable.

Ejemplo:

```bash
python3 ./flow add-project plg-infra --runtime generic --no-compose
```

Comandos actuales:

```bash
python3 ./flow infra plan identity-bootstrap --env staging
python3 ./flow infra apply identity-bootstrap --env staging --approver "platform-owner"
python3 ./flow infra apply identity-bootstrap --env production --approver "platform-owner"
python3 ./flow infra status identity-bootstrap
```

Responsabilidad:

- resolver `infra_targets`
- correr `plan`
- guardar evidencia
- aplicar solo planes aprobados

## Gates del flujo

### Gates humanos

- `spec-approved`
- `plan-approved`
- `merge-approved`
- `staging-approved`
- `production-approved`

### Gates automáticos

- validación de frontmatter
- validación de `targets`
- validación de `[@test]`
- `slice verify`
- CI de repo
- CI del root
- integración/smoke
- validación de release manifest
- plan de infraestructura aprobado

## Qué existe hoy y qué sigue

### Ya implementado

- `flow doctor`
- `flow stack ...`
- `flow tessl ...`
- `flow bmad ...`
- `flow add-project ...`
- `flow spec create|review|approve`
- `flow plan`
- `flow slice start|verify`
- `flow ci spec|repo|integration`
- `flow release cut|manifest|status|promote`
- `flow infra plan|apply|status`
- `flow status`
- workflows del root para CI, release e infra
- workflows mínimos de CI en `backend` y `frontend`

### Siguientes pasos naturales

- publicar artefactos e imágenes por SHA desde `backend` y `frontend`
- conectar `flow release` con un registro de artefactos real
- crear `plg-infra` como repo enrutable para IaC real
- reemplazar los hooks por defecto de `release` e `infra` por integraciones concretas
- automatizar merge y promoción con gates más estrictos

## Siguientes mejoras recomendadas

Orden sugerido:

1. publicar artefactos por SHA desde los submódulos
2. registrar evidencia de CI dentro del manifest de release
3. añadir hooks reales de despliegue por entorno
4. crear `plg-infra`
5. sustituir los hooks de infra por runners de IaC reales
6. automatizar merge/promotion con aprobación por environments

## Regla final

La promoción a `staging` o `production` debe salir desde el root, no desde el submódulo.

Ese es el punto que hace compatible:

- `Spec As Source`
- submódulos Git
- multiagente
- CI/CD auditable
- y release reproducible del sistema completo
