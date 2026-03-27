from __future__ import annotations

import json
import tempfile
from pathlib import Path

from gateway.app.store import TaskStore


def test_enqueue_deduplicates_same_payload_within_window(monkeypatch) -> None:  # type: ignore[override]
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "tasks.db"
        store = TaskStore(db_path)
        store.initialize()

        payload = {"slug": "demo", "title": "Demo", "repos": ["root"]}
        command = ["workflow", "intake", "demo", "--title", "Demo", "--repo", "root"]

        first = store.enqueue(source="github", intent="workflow.intake", payload=payload, command=command, response_target=None)
        second = store.enqueue(source="github", intent="workflow.intake", payload=payload, command=command, response_target=None)

        assert first["task_id"] == second["task_id"]
        assert first["created_at"] == second["created_at"]

