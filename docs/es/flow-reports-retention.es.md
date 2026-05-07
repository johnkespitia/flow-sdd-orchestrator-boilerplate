# Retencion de `.flow/reports/**` (T23)

English source: [docs/flow-reports-retention.md](../flow-reports-retention.md)

Source: `docs/flow-reports-retention.md`  
Last updated: 2026-05-07

## Politica

- Los reportes bajo `.flow/reports/**` son **operativos** (no fuente de verdad en Git). Pueden eliminarse tras el periodo de retencion sin afectar specs en `specs/**`.
- Default recomendado: **30 dias** (`FLOW_REPORTS_RETENTION_DAYS`).

## Ejecucion

```bash
chmod +x scripts/flow_reports_retention.sh
FLOW_WORKSPACE_ROOT=/ruta/al/workspace ./scripts/flow_reports_retention.sh
```

El dry-run lista candidatos. Para borrar:

```bash
FLOW_REPORTS_RETENTION_CONFIRM=1 FLOW_REPORTS_RETENTION_DAYS=30 ./scripts/flow_reports_retention.sh
```

## Integracion CI

Opcional: job mensual con `FLOW_REPORTS_RETENTION_CONFIRM=1` en entorno controlado.

## Evidencia de cierre

- Prueba de regresion canonica: `python3 -m pytest -q gateway/tests/test_ola_d.py -k t23`
