from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


REGISTRY_STATES = [
    "new",
    "triaged",
    "in_edit",
    "in_review",
    "approved",
    "in_execution",
    "in_validation",
    "done",
    "closed",
]
REGISTRY_STATE_INDEX = {name: idx for idx, name in enumerate(REGISTRY_STATES)}


class SpecRegistryError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class TaskStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    command_json TEXT NOT NULL,
                    response_target_json TEXT,
                    status TEXT NOT NULL,
                    stdout TEXT,
                    stderr TEXT,
                    parsed_output_json TEXT,
                    exit_code INTEGER,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS spec_registry (
                    spec_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    assignee TEXT,
                    lock_token TEXT,
                    lock_expires_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS spec_registry_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    spec_id TEXT NOT NULL,
                    event TEXT NOT NULL,
                    from_state TEXT,
                    to_state TEXT,
                    actor TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    source TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_spec_registry_state ON spec_registry(state)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_spec_registry_assignee ON spec_registry(assignee)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_spec_registry_audit_spec ON spec_registry_audit(spec_id, id)"
            )
            connection.commit()

    def reset_running_tasks(self) -> None:
        with self._connect() as connection:
            timestamp = utc_now()
            connection.execute(
                """
                UPDATE tasks
                SET status = 'queued',
                    updated_at = ?,
                    started_at = NULL
                WHERE status = 'running'
                """,
                (timestamp,),
            )
            connection.commit()

    def enqueue(
        self,
        *,
        source: str,
        intent: str,
        payload: dict[str, Any],
        command: list[str],
        response_target: dict[str, Any] | None,
    ) -> dict[str, Any]:
        task_id = uuid.uuid4().hex
        now = utc_now()
        record = {
            "task_id": task_id,
            "source": source,
            "intent": intent,
            "payload_json": json.dumps(payload, ensure_ascii=True),
            "command_json": json.dumps(command, ensure_ascii=True),
            "response_target_json": json.dumps(response_target, ensure_ascii=True) if response_target else None,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks (
                    task_id, source, intent, payload_json, command_json, response_target_json,
                    status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["task_id"],
                    record["source"],
                    record["intent"],
                    record["payload_json"],
                    record["command_json"],
                    record["response_target_json"],
                    record["status"],
                    record["created_at"],
                    record["updated_at"],
                ),
            )
            connection.commit()
        return self.get(task_id)

    def claim_next(self) -> dict[str, Any] | None:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    """
                    SELECT task_id
                    FROM tasks
                    WHERE status = 'queued'
                    ORDER BY created_at ASC
                    LIMIT 1
                    """
                ).fetchone()
                if row is None:
                    connection.commit()
                    return None
                timestamp = utc_now()
                connection.execute(
                    """
                    UPDATE tasks
                    SET status = 'running',
                        started_at = ?,
                        updated_at = ?
                    WHERE task_id = ?
                    """,
                    (timestamp, timestamp, row["task_id"]),
                )
                connection.commit()
        return self.get(str(row["task_id"]))

    def finish(
        self,
        task_id: str,
        *,
        status: str,
        exit_code: int,
        stdout: str,
        stderr: str,
        parsed_output: Any,
    ) -> dict[str, Any]:
        timestamp = utc_now()
        parsed_json = json.dumps(parsed_output, ensure_ascii=True) if parsed_output is not None else None
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE tasks
                SET status = ?,
                    exit_code = ?,
                    stdout = ?,
                    stderr = ?,
                    parsed_output_json = ?,
                    finished_at = ?,
                    updated_at = ?
                WHERE task_id = ?
                """,
                (status, exit_code, stdout, stderr, parsed_json, timestamp, timestamp, task_id),
            )
            connection.commit()
        return self.get(task_id)

    def get(self, task_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(task_id)
        return self._inflate(row)

    def _inflate(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "task_id": row["task_id"],
            "source": row["source"],
            "intent": row["intent"],
            "payload": json.loads(row["payload_json"] or "{}"),
            "command": json.loads(row["command_json"] or "[]"),
            "response_target": json.loads(row["response_target_json"]) if row["response_target_json"] else None,
            "status": row["status"],
            "stdout": row["stdout"],
            "stderr": row["stderr"],
            "parsed_output": json.loads(row["parsed_output_json"]) if row["parsed_output_json"] else None,
            "exit_code": row["exit_code"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "updated_at": row["updated_at"],
        }

    def claim_spec(
        self,
        *,
        spec_id: str,
        actor: str,
        source: str,
        reason: str,
        ttl_seconds: int,
    ) -> dict[str, Any]:
        ttl = self._normalized_ttl(ttl_seconds)
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                record = self._get_or_create_spec_locked(connection, spec_id)
                self._expire_lock_if_needed_locked(connection, record, source)
                if record["lock_token"]:
                    raise SpecRegistryError(
                        "SPEC_ALREADY_CLAIMED",
                        "Spec already claimed by another actor.",
                        409,
                    )
                now = utc_now()
                token = uuid.uuid4().hex
                expires_at = self._iso_after_seconds(ttl)
                connection.execute(
                    """
                    UPDATE spec_registry
                    SET assignee = ?, lock_token = ?, lock_expires_at = ?, updated_at = ?
                    WHERE spec_id = ?
                    """,
                    (actor, token, expires_at, now, spec_id),
                )
                self._append_audit_locked(
                    connection,
                    spec_id=spec_id,
                    event="claim",
                    from_state=str(record["state"]),
                    to_state=str(record["state"]),
                    actor=actor,
                    reason=reason or "claim",
                    source=source,
                )
                connection.commit()
        return self.get_spec(spec_id)

    def heartbeat_spec(
        self,
        *,
        spec_id: str,
        actor: str,
        lock_token: str,
        source: str,
        reason: str,
        ttl_seconds: int,
    ) -> dict[str, Any]:
        ttl = self._normalized_ttl(ttl_seconds)
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                record = self._must_get_spec_locked(connection, spec_id)
                self._expire_lock_if_needed_locked(connection, record, source)
                self._require_lock_owner(record, actor=actor, lock_token=lock_token)
                now = utc_now()
                expires_at = self._iso_after_seconds(ttl)
                connection.execute(
                    """
                    UPDATE spec_registry
                    SET lock_expires_at = ?, updated_at = ?
                    WHERE spec_id = ?
                    """,
                    (expires_at, now, spec_id),
                )
                self._append_audit_locked(
                    connection,
                    spec_id=spec_id,
                    event="heartbeat",
                    from_state=str(record["state"]),
                    to_state=str(record["state"]),
                    actor=actor,
                    reason=reason or "heartbeat",
                    source=source,
                )
                connection.commit()
        return self.get_spec(spec_id)

    def release_spec(
        self,
        *,
        spec_id: str,
        actor: str,
        lock_token: str,
        source: str,
        reason: str,
    ) -> dict[str, Any]:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                record = self._must_get_spec_locked(connection, spec_id)
                self._expire_lock_if_needed_locked(connection, record, source)
                self._require_lock_owner(record, actor=actor, lock_token=lock_token)
                now = utc_now()
                connection.execute(
                    """
                    UPDATE spec_registry
                    SET assignee = NULL, lock_token = NULL, lock_expires_at = NULL, updated_at = ?
                    WHERE spec_id = ?
                    """,
                    (now, spec_id),
                )
                self._append_audit_locked(
                    connection,
                    spec_id=spec_id,
                    event="release",
                    from_state=str(record["state"]),
                    to_state=str(record["state"]),
                    actor=actor,
                    reason=reason or "release",
                    source=source,
                )
                connection.commit()
        return self.get_spec(spec_id)

    def transition_spec(
        self,
        *,
        spec_id: str,
        actor: str,
        to_state: str,
        source: str,
        reason: str,
        lock_token: str | None,
    ) -> dict[str, Any]:
        normalized_to_state = str(to_state).strip()
        if normalized_to_state not in REGISTRY_STATE_INDEX:
            raise SpecRegistryError(
                "INVALID_TRANSITION",
                f"Invalid transition target state: `{normalized_to_state}`.",
                400,
            )
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                record = self._must_get_spec_locked(connection, spec_id)
                self._expire_lock_if_needed_locked(connection, record, source)
                from_state = str(record["state"])
                if REGISTRY_STATE_INDEX[normalized_to_state] != REGISTRY_STATE_INDEX[from_state] + 1:
                    raise SpecRegistryError(
                        "INVALID_TRANSITION",
                        f"Invalid transition: `{from_state}` -> `{normalized_to_state}`.",
                        400,
                    )
                if normalized_to_state in {"in_edit", "in_execution"}:
                    self._require_lock_owner(record, actor=actor, lock_token=lock_token)
                now = utc_now()
                connection.execute(
                    """
                    UPDATE spec_registry
                    SET state = ?, updated_at = ?
                    WHERE spec_id = ?
                    """,
                    (normalized_to_state, now, spec_id),
                )
                self._append_audit_locked(
                    connection,
                    spec_id=spec_id,
                    event="transition",
                    from_state=from_state,
                    to_state=normalized_to_state,
                    actor=actor,
                    reason=reason or "transition",
                    source=source,
                )
                connection.commit()
        return self.get_spec(spec_id)

    def get_spec(self, spec_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM spec_registry WHERE spec_id = ?", (spec_id,)).fetchone()
            if row is None:
                raise KeyError(spec_id)
            record = self._inflate_spec(row)
            audit_rows = connection.execute(
                """
                SELECT event, from_state, to_state, actor, reason, source, timestamp
                FROM spec_registry_audit
                WHERE spec_id = ?
                ORDER BY id ASC
                """,
                (spec_id,),
            ).fetchall()
        record["audit"] = [dict(item) for item in audit_rows]
        return record

    def list_specs(self, *, state: str | None = None, assignee: str | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[str] = []
        if state:
            clauses.append("state = ?")
            params.append(state)
        if assignee:
            clauses.append("assignee = ?")
            params.append(assignee)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT spec_id, state, assignee, lock_token, lock_expires_at, created_at, updated_at
                FROM spec_registry
                {where}
                ORDER BY updated_at DESC, spec_id ASC
                """,
                tuple(params),
            ).fetchall()
        return [{**self._inflate_spec(row), "audit": []} for row in rows]

    def _inflate_spec(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "spec_id": row["spec_id"],
            "state": row["state"],
            "assignee": row["assignee"],
            "lock_token": row["lock_token"],
            "lock_expires_at": row["lock_expires_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _get_or_create_spec_locked(self, connection: sqlite3.Connection, spec_id: str) -> dict[str, Any]:
        row = connection.execute("SELECT * FROM spec_registry WHERE spec_id = ?", (spec_id,)).fetchone()
        if row is not None:
            return self._inflate_spec(row)
        now = utc_now()
        connection.execute(
            """
            INSERT INTO spec_registry (spec_id, state, assignee, lock_token, lock_expires_at, created_at, updated_at)
            VALUES (?, 'new', NULL, NULL, NULL, ?, ?)
            """,
            (spec_id, now, now),
        )
        self._append_audit_locked(
            connection,
            spec_id=spec_id,
            event="created",
            from_state=None,
            to_state="new",
            actor="system",
            reason="auto-create",
            source="gateway",
        )
        row = connection.execute("SELECT * FROM spec_registry WHERE spec_id = ?", (spec_id,)).fetchone()
        if row is None:
            raise SpecRegistryError("REGISTRY_WRITE_FAILED", "Unable to initialize spec registry record.", 500)
        return self._inflate_spec(row)

    def _must_get_spec_locked(self, connection: sqlite3.Connection, spec_id: str) -> dict[str, Any]:
        row = connection.execute("SELECT * FROM spec_registry WHERE spec_id = ?", (spec_id,)).fetchone()
        if row is None:
            raise SpecRegistryError("SPEC_NOT_FOUND", "Spec not found in registry.", 404)
        return self._inflate_spec(row)

    def _append_audit_locked(
        self,
        connection: sqlite3.Connection,
        *,
        spec_id: str,
        event: str,
        from_state: str | None,
        to_state: str | None,
        actor: str,
        reason: str,
        source: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO spec_registry_audit (spec_id, event, from_state, to_state, actor, reason, source, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (spec_id, event, from_state, to_state, actor, reason, source, utc_now()),
        )

    def _require_lock_owner(self, record: dict[str, Any], *, actor: str, lock_token: str | None) -> None:
        if not record.get("lock_token"):
            raise SpecRegistryError("LOCK_REQUIRED", "Spec lock is required for this operation.", 409)
        if str(record.get("assignee") or "") != actor or str(record.get("lock_token") or "") != str(lock_token or ""):
            raise SpecRegistryError("LOCK_MISMATCH", "Spec lock token or assignee mismatch.", 409)

    def _expire_lock_if_needed_locked(
        self,
        connection: sqlite3.Connection,
        record: dict[str, Any],
        source: str,
    ) -> None:
        lock_expires_at = str(record.get("lock_expires_at") or "").strip()
        if not lock_expires_at or not record.get("lock_token"):
            return
        now = datetime.now(timezone.utc)
        try:
            expires = datetime.fromisoformat(lock_expires_at.replace("Z", "+00:00"))
        except ValueError:
            expires = now
        if expires > now:
            return
        connection.execute(
            """
            UPDATE spec_registry
            SET assignee = NULL, lock_token = NULL, lock_expires_at = NULL, updated_at = ?
            WHERE spec_id = ?
            """,
            (utc_now(), record["spec_id"]),
        )
        self._append_audit_locked(
            connection,
            spec_id=str(record["spec_id"]),
            event="lock_expired",
            from_state=str(record["state"]),
            to_state=str(record["state"]),
            actor="system",
            reason="ttl-expired",
            source=source,
        )
        record["assignee"] = None
        record["lock_token"] = None
        record["lock_expires_at"] = None

    def _normalized_ttl(self, ttl_seconds: int) -> int:
        ttl = int(ttl_seconds)
        if ttl < 5 or ttl > 3600:
            raise SpecRegistryError("INVALID_TTL", "TTL must be between 5 and 3600 seconds.", 400)
        return ttl

    def _iso_after_seconds(self, seconds: int) -> str:
        return datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() + float(seconds), tz=timezone.utc).replace(
            microsecond=0
        ).isoformat()
