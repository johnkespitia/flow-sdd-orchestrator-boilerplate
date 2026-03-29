# Retención de `.flow/reports/**` (T23)

## Política

- Reportes bajo `.flow/reports/**` son **operativos** (no fuente de verdad git). Pueden eliminarse tras el período de retención sin afectar specs en `specs/**`.
- Default recomendado: **30 días** (`FLOW_REPORTS_RETENTION_DAYS`).

## Ejecución

```bash
chmod +x scripts/flow_reports_retention.sh
FLOW_WORKSPACE_ROOT=/ruta/al/workspace ./scripts/flow_reports_retention.sh
```

Dry-run lista candidatos. Para borrar:

```bash
FLOW_REPORTS_RETENTION_CONFIRM=1 FLOW_REPORTS_RETENTION_DAYS=30 ./scripts/flow_reports_retention.sh
```

## Integración CI

Opcional: job mensual con `FLOW_REPORTS_RETENTION_CONFIRM=1` en entorno controlado.

## Evidencia de cierre

- Prueba de regresión canónica: `python3 -m pytest -q gateway/tests/test_ola_d.py -k t23`
