# Ajuste de `flow secrets scan` (T21)

English source: [docs/secret-scan-tuning.md](../secret-scan-tuning.md)

Source: `docs/secret-scan-tuning.md`  
Last updated: 2026-05-07

## Falsos positivos

- Variable de entorno `FLOW_SECRET_SCAN_EXTRA_PLACEHOLDER_SUBSTRINGS`: lista separada por comas de subcadenas que deben tratarse como **placeholder** en valores candidatos (reduce falsos positivos en codigo de UI o docs).

## Heuristica

- `secret_value_looks_placeholder` marca valores que parecen codigo, JSX, placeholders o patrones de tokens listados.

## Pruebas

- Ver `flowctl/test_secret_scan_ola_d.py` para casos controlados.
