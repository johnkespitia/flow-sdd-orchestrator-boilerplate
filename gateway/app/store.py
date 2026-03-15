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
