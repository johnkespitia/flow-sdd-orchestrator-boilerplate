# Spec Format

Toda spec del root:

- termina en `.spec.md`
- define `name`, `description`, `status`, `owner` y `targets`
- apunta a archivos reales del root o de los repos configurados en `workspace.config.json`

## Targets

Ejemplos:

- `../../backend/app/**`
- `../../backend/tests/**`
- `../../frontend/src/**`
- `../../.devcontainer/**`

## Tests

Usa `[@test]` para enlazar pruebas reales, por ejemplo:

`[@test] ../../backend/tests/feature/test_identity_bootstrap.py`
