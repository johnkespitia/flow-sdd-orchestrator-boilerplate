# Preflight para promote a staging

English source: [docs/staging-promote-preflight.md](../staging-promote-preflight.md)

Source: `docs/staging-promote-preflight.md`  
Last updated: 2026-05-07

Usa este playbook cuando promociones trabajo a `staging` en SoftOS.

## Los cuatro gates

1. Preparacion local del repo
2. Preparacion de la fuente remota
3. Preparacion de dispatch de workflow
4. Preparacion del rollout en entorno

Si cualquier gate falla, el resultado correcto es `promote blocked`.

## Preflight minimo

- cambios committeados
- rama source pusheada
- runtime de dispatch confirmado
- `gh` confirmado dentro del devcontainer `workspace`
- auth confirmada en ese runtime
- inputs de workflow conocidos
- migraciones sensibles a rollout siguen gateadas

## Regla de runtime

En este workspace, `gh` se espera instalado en el servicio `workspace` del devcontainer.

Por tanto:

- que falte `gh` en el host no es el bloqueo relevante
- el bloqueo relevante es auth faltante o dispatch no usable dentro de `workspace`

## Modelo de decision

Solo dos salidas son validas:

- `promote dispatchable`
- `promote blocked`

## Regla importante

No confundir:

- "implementado localmente"

con

- "promovible a staging"

Un promote a staging es real solo cuando el ref remoto, el mecanismo de dispatch y el gate de rollout estan listos.
