from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_global_lock_db_path(root: Path) -> Path:
    return root / ".flow" / "state" / "locks.db"


class GlobalLockError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class SQLiteGlobalLockBackend:
    def __init__(self, database_path: Path, *, utc_now_fn: Callable[[], str] = utc_now) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._utc_now = utc_now_fn
        self._mutex = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS global_locks (
                    lock_name TEXT PRIMARY KEY,
                    scope TEXT NOT NULL,
                    repo TEXT NOT NULL,
                    owner_run_id TEXT NOT NULL,
                    owner_feature TEXT NOT NULL,
                    owner_slice TEXT NOT NULL,
                    acquired_at TEXT NOT NULL,
                    heartbeat_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS global_lock_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lock_name TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor_run_id TEXT,
                    feature_slug TEXT,
                    slice_name TEXT,
                    timestamp TEXT NOT NULL,
                    details TEXT
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_global_locks_scope_repo ON global_locks(scope, repo)")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_global_lock_events_name_id ON global_lock_events(lock_name, event_id)"
            )
            connection.commit()

    def acquire(
        self,
        *,
        lock_name: str,
        scope: str,
        repo: str,
        owner_run_id: str,
        owner_feature: str,
        owner_slice: str,
        ttl_seconds: int,
        details: str = "",
    ) -> dict[str, object]:
        now = self._utc_now()
        expires_at = self._expires_at(now, ttl_seconds)
        with self._mutex:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._expire_stale_locked(connection, now)
                row = self._get_lock_locked(connection, lock_name)
                if row is not None:
                    owner_matches = (
                        str(row["owner_run_id"]) == owner_run_id
                        and str(row["owner_feature"]) == owner_feature
                        and str(row["owner_slice"]) == owner_slice
                    )
                    if owner_matches:
                        connection.execute(
                            """
                            UPDATE global_locks
                            SET scope = ?, repo = ?, heartbeat_at = ?, expires_at = ?
                            WHERE lock_name = ?
                            """,
                            (scope, repo, now, expires_at, lock_name),
                        )
                        self._record_event_locked(
                            connection,
                            lock_name=lock_name,
                            event_type="heartbeat-renew",
                            actor_run_id=owner_run_id,
                            feature_slug=owner_feature,
                            slice_name=owner_slice,
                            timestamp=now,
                            details=details or "owner-renew",
                        )
                        connection.commit()
                        return {
                            "granted": True,
                            "status": "renewed",
                            "lock_name": lock_name,
                            "scope": scope,
                            "repo": repo,
                            "owner_run_id": owner_run_id,
                            "owner_feature": owner_feature,
                            "owner_slice": owner_slice,
                            "acquired_at": str(row["acquired_at"]),
                            "heartbeat_at": now,
                            "expires_at": expires_at,
                        }
                    self._record_event_locked(
                        connection,
                        lock_name=lock_name,
                        event_type="denied",
                        actor_run_id=owner_run_id,
                        feature_slug=owner_feature,
                        slice_name=owner_slice,
                        timestamp=now,
                        details=f"owned-by:{row['owner_run_id']}:{row['owner_feature']}:{row['owner_slice']}",
                    )
                    connection.commit()
                    return {
                        "granted": False,
                        "status": "denied",
                        "lock_name": lock_name,
                        "scope": str(row["scope"]),
                        "repo": str(row["repo"]),
                        "owner_run_id": str(row["owner_run_id"]),
                        "owner_feature": str(row["owner_feature"]),
                        "owner_slice": str(row["owner_slice"]),
                        "acquired_at": str(row["acquired_at"]),
                        "heartbeat_at": str(row["heartbeat_at"]),
                        "expires_at": str(row["expires_at"]),
                    }
                connection.execute(
                    """
                    INSERT INTO global_locks (
                        lock_name, scope, repo, owner_run_id, owner_feature, owner_slice, acquired_at, heartbeat_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (lock_name, scope, repo, owner_run_id, owner_feature, owner_slice, now, now, expires_at),
                )
                self._record_event_locked(
                    connection,
                    lock_name=lock_name,
                    event_type="acquire",
                    actor_run_id=owner_run_id,
                    feature_slug=owner_feature,
                    slice_name=owner_slice,
                    timestamp=now,
                    details=details or "new-lock",
                )
                connection.commit()
                return {
                    "granted": True,
                    "status": "acquired",
                    "lock_name": lock_name,
                    "scope": scope,
                    "repo": repo,
                    "owner_run_id": owner_run_id,
                    "owner_feature": owner_feature,
                    "owner_slice": owner_slice,
                    "acquired_at": now,
                    "heartbeat_at": now,
                    "expires_at": expires_at,
                }

    def heartbeat(
        self,
        *,
        lock_name: str,
        owner_run_id: str,
        owner_feature: str,
        owner_slice: str,
        ttl_seconds: int,
        details: str = "",
    ) -> dict[str, object]:
        now = self._utc_now()
        expires_at = self._expires_at(now, ttl_seconds)
        with self._mutex:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._expire_stale_locked(connection, now)
                row = self._get_lock_locked(connection, lock_name)
                if row is None:
                    raise GlobalLockError("LOCK_NOT_FOUND", f"Lock `{lock_name}` does not exist.")
                if not self._row_owned_by(row, owner_run_id=owner_run_id, owner_feature=owner_feature, owner_slice=owner_slice):
                    raise GlobalLockError("LOCK_NOT_OWNED", f"Lock `{lock_name}` is owned by another run.")
                connection.execute(
                    "UPDATE global_locks SET heartbeat_at = ?, expires_at = ? WHERE lock_name = ?",
                    (now, expires_at, lock_name),
                )
                self._record_event_locked(
                    connection,
                    lock_name=lock_name,
                    event_type="heartbeat",
                    actor_run_id=owner_run_id,
                    feature_slug=owner_feature,
                    slice_name=owner_slice,
                    timestamp=now,
                    details=details or "heartbeat",
                )
                connection.commit()
                return {
                    "granted": True,
                    "status": "heartbeat",
                    "lock_name": lock_name,
                    "scope": str(row["scope"]),
                    "repo": str(row["repo"]),
                    "owner_run_id": owner_run_id,
                    "owner_feature": owner_feature,
                    "owner_slice": owner_slice,
                    "acquired_at": str(row["acquired_at"]),
                    "heartbeat_at": now,
                    "expires_at": expires_at,
                }

    def release(
        self,
        *,
        lock_name: str,
        owner_run_id: str,
        owner_feature: str,
        owner_slice: str,
        details: str = "",
    ) -> dict[str, object]:
        now = self._utc_now()
        with self._mutex:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = self._get_lock_locked(connection, lock_name)
                if row is None:
                    return {"released": False, "status": "missing", "lock_name": lock_name}
                if not self._row_owned_by(row, owner_run_id=owner_run_id, owner_feature=owner_feature, owner_slice=owner_slice):
                    raise GlobalLockError("LOCK_NOT_OWNED", f"Lock `{lock_name}` is owned by another run.")
                connection.execute("DELETE FROM global_locks WHERE lock_name = ?", (lock_name,))
                self._record_event_locked(
                    connection,
                    lock_name=lock_name,
                    event_type="release",
                    actor_run_id=owner_run_id,
                    feature_slug=owner_feature,
                    slice_name=owner_slice,
                    timestamp=now,
                    details=details or "release",
                )
                connection.commit()
                return {
                    "released": True,
                    "status": "released",
                    "lock_name": lock_name,
                    "scope": str(row["scope"]),
                    "repo": str(row["repo"]),
                    "owner_run_id": str(row["owner_run_id"]),
                    "owner_feature": str(row["owner_feature"]),
                    "owner_slice": str(row["owner_slice"]),
                }

    def expire_stale(self) -> list[dict[str, object]]:
        now = self._utc_now()
        with self._mutex:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                expired = self._expire_stale_locked(connection, now)
                connection.commit()
                return expired

    def get_lock(self, lock_name: str) -> dict[str, object] | None:
        with self._connect() as connection:
            row = self._get_lock_locked(connection, lock_name)
            if row is None:
                return None
            return self._inflate_lock(row)

    def list_locks(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM global_locks ORDER BY lock_name ASC").fetchall()
            return [self._inflate_lock(row) for row in rows]

    def list_events(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT event_id, lock_name, event_type, actor_run_id, feature_slug, slice_name, timestamp, details
                FROM global_lock_events
                ORDER BY event_id ASC
                """
            ).fetchall()
            return [
                {
                    "event_id": int(row["event_id"]),
                    "lock_name": str(row["lock_name"]),
                    "event_type": str(row["event_type"]),
                    "actor_run_id": str(row["actor_run_id"] or ""),
                    "feature_slug": str(row["feature_slug"] or ""),
                    "slice_name": str(row["slice_name"] or ""),
                    "timestamp": str(row["timestamp"]),
                    "details": str(row["details"] or ""),
                }
                for row in rows
            ]

    def _expire_stale_locked(self, connection: sqlite3.Connection, now: str) -> list[dict[str, object]]:
        rows = connection.execute("SELECT * FROM global_locks WHERE expires_at <= ?", (now,)).fetchall()
        expired: list[dict[str, object]] = []
        for row in rows:
            payload = self._inflate_lock(row)
            expired.append(payload)
            connection.execute("DELETE FROM global_locks WHERE lock_name = ?", (str(row["lock_name"]),))
            self._record_event_locked(
                connection,
                lock_name=str(row["lock_name"]),
                event_type="expire",
                actor_run_id=str(row["owner_run_id"]),
                feature_slug=str(row["owner_feature"]),
                slice_name=str(row["owner_slice"]),
                timestamp=now,
                details="ttl-expired",
            )
        return expired

    def _get_lock_locked(self, connection: sqlite3.Connection, lock_name: str) -> sqlite3.Row | None:
        return connection.execute("SELECT * FROM global_locks WHERE lock_name = ?", (lock_name,)).fetchone()

    def _record_event_locked(
        self,
        connection: sqlite3.Connection,
        *,
        lock_name: str,
        event_type: str,
        actor_run_id: str,
        feature_slug: str,
        slice_name: str,
        timestamp: str,
        details: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO global_lock_events (
                lock_name, event_type, actor_run_id, feature_slug, slice_name, timestamp, details
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (lock_name, event_type, actor_run_id, feature_slug, slice_name, timestamp, details),
        )

    @staticmethod
    def _row_owned_by(
        row: sqlite3.Row,
        *,
        owner_run_id: str,
        owner_feature: str,
        owner_slice: str,
    ) -> bool:
        return (
            str(row["owner_run_id"]) == owner_run_id
            and str(row["owner_feature"]) == owner_feature
            and str(row["owner_slice"]) == owner_slice
        )

    @staticmethod
    def _inflate_lock(row: sqlite3.Row) -> dict[str, object]:
        return {
            "lock_name": str(row["lock_name"]),
            "scope": str(row["scope"]),
            "repo": str(row["repo"]),
            "owner_run_id": str(row["owner_run_id"]),
            "owner_feature": str(row["owner_feature"]),
            "owner_slice": str(row["owner_slice"]),
            "acquired_at": str(row["acquired_at"]),
            "heartbeat_at": str(row["heartbeat_at"]),
            "expires_at": str(row["expires_at"]),
        }

    @staticmethod
    def _expires_at(now: str, ttl_seconds: int) -> str:
        base = datetime.fromisoformat(now)
        ttl = max(1, int(ttl_seconds))
        return (base + timedelta(seconds=ttl)).replace(microsecond=0).isoformat()
