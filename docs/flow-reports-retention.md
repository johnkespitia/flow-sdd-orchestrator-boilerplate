# `.flow/reports/**` Retention (T23)

Spanish mirror: [docs/es/flow-reports-retention.es.md](./es/flow-reports-retention.es.md)

Source: `docs/flow-reports-retention.md`  
Last updated: 2026-05-07

## Policy

- Reports under `.flow/reports/**` are **operational** (not Git source of truth). They can be removed after the retention period without affecting specs in `specs/**`.
- Recommended default: **30 days** (`FLOW_REPORTS_RETENTION_DAYS`).

## Execution

```bash
chmod +x scripts/flow_reports_retention.sh
FLOW_WORKSPACE_ROOT=/path/to/workspace ./scripts/flow_reports_retention.sh
```

Dry-run lists candidates. To delete:

```bash
FLOW_REPORTS_RETENTION_CONFIRM=1 FLOW_REPORTS_RETENTION_DAYS=30 ./scripts/flow_reports_retention.sh
```

## CI integration

Optional: monthly job with `FLOW_REPORTS_RETENTION_CONFIRM=1` in a controlled environment.

## Closure evidence

- Canonical regression test: `python3 -m pytest -q gateway/tests/test_ola_d.py -k t23`
