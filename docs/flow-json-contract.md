# Flow JSON Contract

`flow` sigue entregando salida legible por humanos por defecto, pero los comandos operativos del
control plane aceptan `--json` para agentes, CI y tooling.

## Comandos cubiertos

- `doctor`
- `status`
- `skills doctor|list|sync`
- `providers doctor|list`
- `submodule doctor|sync`
- `secrets doctor|list|sync|exec|scan`
- `drift check`
- `contract verify`
- `ci spec|repo|integration`
- `release cut|manifest|status|promote`
- `infra plan|apply|status`
- `spec generate-contracts`

## Convención

- siempre imprimir un único objeto JSON en `stdout`
- errores operativos devuelven exit code distinto de `0`
- reportes persistidos siguen viviendo en `.flow/reports/**` o `releases/**`
- el payload debe incluir rutas relativas del repo cuando referencia artefactos

## Ejemplos

```bash
python3 ./flow doctor --json
python3 ./flow ci spec --all --json
python3 ./flow submodule doctor --json
python3 ./flow secrets scan --all --json
python3 ./flow contract verify --all --json
python3 ./flow release status --version 2026.03.14-1 --json
```
