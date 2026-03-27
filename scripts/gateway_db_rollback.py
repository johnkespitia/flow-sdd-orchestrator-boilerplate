#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import psycopg2


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
    parser.add_argument("--to", choices=["sqlite"], default="sqlite", help="Rollback target backend.")
    parser.add_argument("--postgres-url", help="Postgres source URL for rollback drill.")
    parser.add_argument("--sqlite-path", help="SQLite target path for rollback drill.")
    args = parser.parse_args()

    if args.postgres_url and args.sqlite_path:
        sqlite_path = Path(args.sqlite_path).resolve()
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        pg_conn = psycopg2.connect(args.postgres_url)
        dst = _connect_sqlite(sqlite_path)
        try:
            _ensure_schema(dst)
            with pg_conn.cursor() as cur:
                for table in TABLES:
                    cur.execute(f"SELECT * FROM {table}")
                    rows = cur.fetchall()
                    cols = [desc[0] for desc in cur.description] if cur.description else []
                    dst.execute(f"DELETE FROM {table}")
                    if rows and cols:
                        placeholders = ", ".join("?" for _ in cols)
                        col_list = ", ".join(cols)
                        dst.executemany(
                            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})",
                            [tuple(row) for row in rows],
                        )
            dst.commit()
        finally:
            pg_conn.close()
            dst.close()
        print({"status": "ok", "action": "postgres_to_sqlite", "sqlite_path": str(sqlite_path)})
        return 0

    print(
        {
            "status": "manual",
            "action": "unset_db_url",
            "instructions": [
                "1) Deshabilita Postgres removiendo SOFTOS_GATEWAY_DB_URL del entorno del gateway.",
                "2) Asegura que SOFTOS_GATEWAY_DB apunte al archivo SQLite esperado.",
                "3) Reinicia el gateway y valida /healthz y /metrics.",
                "4) Para rollback drill automatizado, usa --postgres-url y --sqlite-path.",
            ],
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

