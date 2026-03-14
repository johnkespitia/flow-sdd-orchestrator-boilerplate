# Flow State

`.flow/` guarda el estado operativo del SDLC agentico sin competir con `specs/**`.

Los archivos generados en `state/`, `plans/`, `reports/` y `runs/` son artefactos locales del
workspace. El repo solo versiona placeholders y documentacion; el contenido generado se ignora por
Git.

## Layout

- `state/`: estado por feature o spec
- `plans/`: planes de slices y worktrees
- `reports/`: review, QA y handoffs
- `runs/`: artefactos efimeros de ejecucion local

## Regla

La fuente de verdad sigue viviendo en `specs/**`.

Los agentes pueden leer `.flow/**` para saber que sigue, pero nunca deben tratar esos archivos
como reemplazo de la spec.
