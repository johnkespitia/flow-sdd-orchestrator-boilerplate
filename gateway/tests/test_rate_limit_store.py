from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from gateway.app.store import TaskStore


def test_rate_limit_persists_across_store_instances(tmp_path: Path) -> None:
    db_path = tmp_path / "gateway-rate-limit.db"
    first = TaskStore(db_path)
    first.initialize()
    second = TaskStore(db_path)
    second.initialize()

    a = first.check_rate_limit(
        source="github",
        endpoint="/webhooks/github",
        actor_key="1.2.3.4",
        window_seconds=30,
        max_requests=2,
    )
    b = second.check_rate_limit(
        source="github",
        endpoint="/webhooks/github",
        actor_key="1.2.3.4",
        window_seconds=30,
        max_requests=2,
    )
    c = second.check_rate_limit(
        source="github",
        endpoint="/webhooks/github",
        actor_key="1.2.3.4",
        window_seconds=30,
        max_requests=2,
    )
    assert a["allowed"] is True
    assert b["allowed"] is True
    assert c["allowed"] is False


def test_rate_limit_window_rolls_over(tmp_path: Path) -> None:
    db_path = tmp_path / "gateway-rate-limit-window.db"
    store = TaskStore(db_path)
    store.initialize()
    first = store.check_rate_limit(
        source="jira",
        endpoint="/webhooks/jira",
        actor_key="agent-1",
        window_seconds=1,
        max_requests=1,
    )
    second = store.check_rate_limit(
        source="jira",
        endpoint="/webhooks/jira",
        actor_key="agent-1",
        window_seconds=1,
        max_requests=1,
    )
    assert first["allowed"] is True
    assert second["allowed"] is False
    time.sleep(1.1)
    third = store.check_rate_limit(
        source="jira",
        endpoint="/webhooks/jira",
        actor_key="agent-1",
        window_seconds=1,
        max_requests=1,
    )
    assert third["allowed"] is True


@pytest.mark.skipif(not os.getenv("SOFTOS_TEST_POSTGRES_URL"), reason="SOFTOS_TEST_POSTGRES_URL not set")
def test_rate_limit_postgres_backend_supported(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "unused.db", database_url=os.getenv("SOFTOS_TEST_POSTGRES_URL"))
    store.initialize()
    one = store.check_rate_limit(
        source="slack",
        endpoint="/webhooks/slack/commands",
        actor_key="actor-x",
        window_seconds=30,
        max_requests=1,
    )
    two = store.check_rate_limit(
        source="slack",
        endpoint="/webhooks/slack/commands",
        actor_key="actor-x",
        window_seconds=30,
        max_requests=1,
    )
    assert one["allowed"] is True
    assert two["allowed"] is False

