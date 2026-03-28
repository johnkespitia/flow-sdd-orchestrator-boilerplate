#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

try:
    import psycopg2
except Exception:  # pragma: no cover - optional for sqlite-only runs
    psycopg2 = None  # type: ignore[assignment]


TABLES = [
    "tasks",
    "task_events",
    "task_timeline",
    "intake_failures",
    "spec_registry",
    "spec_registry_audit",
    "auth_audit",
]


def _connect_sqlite(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    # Minimal schema creation for target sqlite:///. For Postgres, run in central env.
    conn.executescript(
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
        );
        CREATE TABLE IF NOT EXISTS task_timeline (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            actor TEXT NOT NULL,
            message TEXT NOT NULL,
            source TEXT NOT NULL,
            direction TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS task_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            event TEXT NOT NULL,
            source TEXT NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS intake_failures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            reason TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS spec_registry (
            spec_id TEXT PRIMARY KEY,
            state TEXT NOT NULL,
            assignee TEXT,
            lock_token TEXT,
            lock_expires_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
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
        );
        CREATE TABLE IF NOT EXISTS auth_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor TEXT,
            source TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            decision TEXT NOT NULL,
            reason_code TEXT NOT NULL,
            correlation_id TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite-path", required=True)
    parser.add_argument("--target-url", required=True, help="Target DB URL. 8A supports sqlite:///... for migration tests.")
    args = parser.parse_args()

    sqlite_path = Path(args.sqlite_path).resolve()
    target_url = str(args.target_url).strip()
    src = _connect_sqlite(sqlite_path)
    try:
        if target_url.lower().startswith("sqlite:///"):
            target_path = Path(target_url[len("sqlite:///") :]).resolve()
            target_path.parent.mkdir(parents=True, exist_ok=True)
            dst = _connect_sqlite(target_path)
            try:
                _ensure_schema(dst)
                for table in TABLES:
                    try:
                        rows = src.execute(f"SELECT * FROM {table}").fetchall()
                    except sqlite3.OperationalError:
                        continue
                    if not rows:
                        continue
                    cols = rows[0].keys()
                    placeholders = ", ".join("?" for _ in cols)
                    col_list = ", ".join(cols)
                    dst.execute(f"DELETE FROM {table}")
                    dst.executemany(
                        f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})",
                        [tuple(row[col] for col in cols) for row in rows],
                    )
                dst.commit()
            finally:
                dst.close()
            print({"status": "ok", "sqlite": str(sqlite_path), "target": str(target_path), "backend": "sqlite"})
            return 0

        if target_url.lower().startswith("postgresql://") or target_url.lower().startswith("postgres://"):
            if psycopg2 is None:
                raise SystemExit("Postgres backend requires psycopg2 to be installed.")
            conn = psycopg2.connect(target_url)
            try:
                with conn.cursor() as cur:
                    cur.execute(
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
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS task_timeline (
                            id BIGINT PRIMARY KEY,
                            task_id TEXT NOT NULL,
                            actor TEXT NOT NULL,
                            message TEXT NOT NULL,
                            source TEXT NOT NULL,
                            direction TEXT NOT NULL,
                            created_at TEXT NOT NULL
                        )
                        """
                    )
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS task_events (
                            id BIGINT PRIMARY KEY,
                            task_id TEXT,
                            event TEXT NOT NULL,
                            source TEXT NOT NULL,
                            status TEXT NOT NULL,
                            payload_json TEXT NOT NULL,
                            created_at TEXT NOT NULL
                        )
                        """
                    )
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS intake_failures (
                            id BIGINT PRIMARY KEY,
                            source TEXT NOT NULL,
                            reason TEXT NOT NULL,
                            payload_json TEXT NOT NULL,
                            created_at TEXT NOT NULL
                        )
                        """
                    )
                    cur.execute(
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
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS spec_registry_audit (
                            id BIGINT PRIMARY KEY,
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
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS auth_audit (
                            id BIGINT PRIMARY KEY,
                            actor TEXT,
                            source TEXT NOT NULL,
                            endpoint TEXT NOT NULL,
                            decision TEXT NOT NULL,
                            reason_code TEXT NOT NULL,
                            correlation_id TEXT,
                            created_at TEXT NOT NULL
                        )
                        """
                    )
                    for table in TABLES:
                        cur.execute(f"DELETE FROM {table}")
                    conn.commit()

                    for table in TABLES:
                        try:
                            rows = src.execute(f"SELECT * FROM {table}").fetchall()
                        except sqlite3.OperationalError:
                            continue
                        if not rows:
                            continue
                        cols = list(rows[0].keys())
                        col_list = ", ".join(cols)
                        placeholders = ", ".join("%s" for _ in cols)
                        values = [tuple(row[col] for col in cols) for row in rows]
                        cur.executemany(f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})", values)
                    conn.commit()
            finally:
                conn.close()
            print({"status": "ok", "sqlite": str(sqlite_path), "target": target_url, "backend": "postgres"})
            return 0
    finally:
        src.close()

    raise SystemExit("Unsupported target URL. Use sqlite:///... or postgresql://...")


if __name__ == "__main__":
    raise SystemExit(main())
