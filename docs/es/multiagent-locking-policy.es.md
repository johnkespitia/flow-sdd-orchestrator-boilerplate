# Multiagent locking policy

English source: [docs/multiagent-locking-policy.md](../multiagent-locking-policy.md)

Source: `docs/multiagent-locking-policy.md`  
Last updated: 2026-05-06

Nota: Este espejo en espanol fue creado para cerrar el backlog de i18n. Se recomienda refinar la traduccion en una iteracion posterior.

# Multiagent Locking Policy

Spanish mirror: [docs/es/multiagent-locking-policy.es.md](./es/multiagent-locking-policy.es.md)

Source: `docs/multiagent-locking-policy.md`  
Last updated: 2026-05-06

## Lock Rules

| Lock type | Scope | TTL | Acquire | Release |
| --- | --- | --- | --- | --- |
| `semantic-lock` | Slice semantic resource (`db:migrations`, `api:routes`, `contracts:schema`) | `FLOW_SCHEDULER_LOCK_TTL_SECONDS` (default 120s) | Before slice execution | On success, failure, or timeout eviction |
| `repo-capacity` | Repo execution lane | N/A (capacity gate) | Before scheduling slice | After slice finishes |
| `hot-area-capacity` | Derived path hot area (`dir/subdir`) | N/A (capacity gate) | Before scheduling slice | After slice finishes |
| `overlap-preflight` | Critical write-set overlap by real targets | N/A (safety gate) | Preflight/scheduling | Not applicable |

## Safety Guarantees

- No duplicate execution for the same slice under concurrent workers.
- DAG dependencies (`depends_on`) block children until parents pass.
- Retry only applies to execution failures; exhausted retries move slice to DLQ.
- Scheduler reports include queue, capacity, waits, locks, DLQ, and traceability.
