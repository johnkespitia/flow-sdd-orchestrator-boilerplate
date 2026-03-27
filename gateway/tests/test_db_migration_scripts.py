from __future__ import annotations

import json
import sqlite3
import subprocess
import tempfile
from pathlib import Path


def _seed_sqlite(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS tasks (task_id TEXT PRIMARY KEY, source TEXT, intent TEXT, payload_json TEXT, command_json TEXT, response_target_json TEXT, status TEXT, stdout TEXT, stderr TEXT, parsed_output_json TEXT, exit_code INTEGER, created_at TEXT, started_at TEXT, finished_at TEXT, updated_at TEXT)")
        conn.execute("INSERT INTO tasks (task_id, source, intent, payload_json, command_json, response_target_json, status, stdout, stderr, parsed_output_json, exit_code, created_at, started_at, finished_at, updated_at) VALUES ('t1','api','status.get','{}','[]',NULL,'queued',NULL,NULL,NULL,NULL,'2026-01-01T00:00:00+00:00',NULL,NULL,'2026-01-01T00:00:00+00:00')")
        conn.commit()
    finally:
        conn.close()


def test_migrate_and_verify_scripts_sqlite_target() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory() as tmp:
        source_db = Path(tmp) / "source.db"
        target_db = Path(tmp) / "target.db"
        _seed_sqlite(source_db)
        migrate = subprocess.run(
            ["python3", str(repo_root / "scripts" / "gateway_db_migrate_up.py"), "--sqlite-path", str(source_db), "--target-url", f"sqlite:///{target_db}"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        assert migrate.returncode == 0, migrate.stdout + migrate.stderr
        verify = subprocess.run(
            ["python3", str(repo_root / "scripts" / "gateway_db_verify.py"), "--sqlite-path", str(source_db), "--target-url", f"sqlite:///{target_db}"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        assert verify.returncode == 0, verify.stdout + verify.stderr

