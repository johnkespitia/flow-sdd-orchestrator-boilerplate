from __future__ import annotations

import tempfile
from pathlib import Path

from gateway.app.store import TaskStore


def test_auth_audit_persists_entries() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "tasks.db"
        store = TaskStore(db_path)
        store.initialize()
        store.record_auth_audit(
            actor="alice",
            source="api",
            endpoint="/v1/intents",
            decision="accepted",
            reason_code="API_TOKEN_OK",
            correlation_id="req-1",
        )
        items = store.list_auth_audit(limit=10)
        assert len(items) == 1
        assert items[0]["actor"] == "alice"
        assert items[0]["decision"] == "accepted"

