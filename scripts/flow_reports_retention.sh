#!/usr/bin/env bash
# T23: política de retención para `.flow/reports/**` (dry-run por defecto).
set -euo pipefail
ROOT="${FLOW_WORKSPACE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
DAYS="${FLOW_REPORTS_RETENTION_DAYS:-30}"
REPORTS="${ROOT}/.flow/reports"
if [[ ! -d "${REPORTS}" ]]; then
  echo "No hay ${REPORTS}; nada que hacer."
  exit 0
fi
echo "Politica: borrar archivos más antiguos que ${DAYS} días bajo ${REPORTS}"
if [[ "${FLOW_REPORTS_RETENTION_CONFIRM:-0}" != "1" ]]; then
  find "${REPORTS}" -type f -mtime "+${DAYS}" -print || true
  echo "Dry-run. Exporta FLOW_REPORTS_RETENTION_CONFIRM=1 para eliminar."
  exit 0
fi
find "${REPORTS}" -type f -mtime "+${DAYS}" -delete
echo "Limpieza aplicada."
