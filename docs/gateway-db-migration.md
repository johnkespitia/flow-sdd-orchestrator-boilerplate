## Gateway DB Migration (SQLite -> Postgres)

### Objetivo

Habilitar Postgres como backend operativo principal del gateway mediante `SOFTOS_GATEWAY_DB_URL`, manteniendo compatibilidad con SQLite.

Los scripts soportan `sqlite:///...` y `postgresql://...` para validación local o central.

### Configuración

- **SQLite (default)**:
  - `SOFTOS_GATEWAY_DB=/path/a/tasks.db`
  - `SOFTOS_GATEWAY_DB_URL` **no** seteado.

- **Postgres (central)**:
  - `SOFTOS_GATEWAY_DB_URL=postgresql://user:pass@host:5432/dbname`
  - Mantener `SOFTOS_GATEWAY_DB` como fallback/rollback.

### Migración (local testable con sqlite target)

```bash
python3 scripts/gateway_db_migrate_up.py \
  --sqlite-path "$SOFTOS_GATEWAY_DB" \
  --target-url "sqlite:///$(pwd)/.tmp/gateway-postgres-sim.db"

python3 scripts/gateway_db_verify.py \
  --sqlite-path "$SOFTOS_GATEWAY_DB" \
  --target-url "sqlite:///$(pwd)/.tmp/gateway-postgres-sim.db"
```

### Migración (Postgres real)

Requiere driver y conectividad Postgres:

```bash
python3 scripts/gateway_db_migrate_up.py \
  --sqlite-path "$SOFTOS_GATEWAY_DB" \
  --target-url "postgresql://user:pass@host:5432/dbname"

python3 scripts/gateway_db_verify.py \
  --sqlite-path "$SOFTOS_GATEWAY_DB" \
  --target-url "postgresql://user:pass@host:5432/dbname"
```

### Verify integrity

- `gateway_db_verify.py` compara conteos por tabla entre source y target:
  - `tasks`
  - `task_events`
  - `task_timeline`
  - `intake_failures`
  - `spec_registry`
  - `spec_registry_audit`
  - `auth_audit`

### Rollback operativo

Rollback por configuración (manual):

```bash
python3 scripts/gateway_db_rollback.py --to sqlite
```

Pasos:

1. Remover `SOFTOS_GATEWAY_DB_URL` del entorno del gateway.
2. Asegurar `SOFTOS_GATEWAY_DB` apuntando al SQLite esperado.
3. Reiniciar gateway y validar:
   - `GET /healthz`
   - `GET /metrics`

Rollback drill automatizado Postgres -> SQLite:

```bash
python3 scripts/gateway_db_rollback.py \
  --to sqlite \
  --postgres-url "postgresql://user:pass@host:5432/dbname" \
  --sqlite-path "$(pwd)/gateway/data/tasks.rollback.db"

python3 scripts/gateway_db_verify.py \
  --sqlite-path "$SOFTOS_GATEWAY_DB" \
  --target-url "sqlite:///$(pwd)/gateway/data/tasks.rollback.db"
```

