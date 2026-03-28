# Ajuste de `flow secrets scan` (T21)

## Falsos positivos

- Variable de entorno `FLOW_SECRET_SCAN_EXTRA_PLACEHOLDER_SUBSTRINGS`: lista separada por comas de subcadenas que deben tratarse como **placeholder** en valores candidatos (reduce FP en código de UI o docs).

## Heurística

- `secret_value_looks_placeholder` marca valores que parecen código, JSX, placeholders o tokens listados.

## Pruebas

- Ver `flowctl/test_secret_scan_ola_d.py` para casos controlados.
