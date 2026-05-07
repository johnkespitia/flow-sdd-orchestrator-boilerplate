# `flow secrets scan` Tuning (T21)

Spanish mirror: [docs/es/secret-scan-tuning.es.md](./es/secret-scan-tuning.es.md)

Source: `docs/secret-scan-tuning.md`  
Last updated: 2026-05-07

## False positives

- Environment variable `FLOW_SECRET_SCAN_EXTRA_PLACEHOLDER_SUBSTRINGS`: comma-separated list of substrings to treat as **placeholders** in candidate values (reduces false positives in UI code or docs).

## Heuristic

- `secret_value_looks_placeholder` marks values that look like code, JSX, placeholders, or listed token patterns.

## Tests

- See `flowctl/test_secret_scan_ola_d.py` for controlled cases.
