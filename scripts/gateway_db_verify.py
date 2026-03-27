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


def _sqlite_count(path: Path, table: str) -> int:
    conn = sqlite3.connect(path)
    try:
        row = conn.execute(f"SELECT COUNT(1) FROM {table}").fetchone()
        return int(row[0] or 0) if row else 0
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite-path", required=True)
    parser.add_argument("--target-url", required=True, help="Target DB URL. 8A supports sqlite:///... for verification.")
    args = parser.parse_args()

    sqlite_path = Path(args.sqlite_path).resolve()
    target_url = str(args.target_url).strip()
    report = {"sqlite": str(sqlite_path), "target": target_url, "tables": []}
    ok = True
    if target_url.lower().startswith("sqlite:///"):
        target_path = Path(target_url[len("sqlite:///") :]).resolve()
        report["target"] = str(target_path)
        for table in TABLES:
            left = _sqlite_count(sqlite_path, table)
            right = _sqlite_count(target_path, table)
            report["tables"].append({"table": table, "sqlite_count": left, "target_count": right, "match": left == right})
            ok = ok and (left == right)
        print(report)
        return 0 if ok else 1

    if target_url.lower().startswith("postgresql://") or target_url.lower().startswith("postgres://"):
        conn = psycopg2.connect(target_url)
        try:
            with conn.cursor() as cur:
                for table in TABLES:
                    left = _sqlite_count(sqlite_path, table)
                    cur.execute(f"SELECT COUNT(1) FROM {table}")
                    row = cur.fetchone()
                    right = int(row[0] or 0) if row else 0
                    report["tables"].append({"table": table, "sqlite_count": left, "target_count": right, "match": left == right})
                    ok = ok and (left == right)
        finally:
            conn.close()
        print(report)
        return 0 if ok else 1

    raise SystemExit("Unsupported target URL. Use sqlite:///... or postgresql://...")


if __name__ == "__main__":
    raise SystemExit(main())

