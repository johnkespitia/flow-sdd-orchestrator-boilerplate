from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path

from gateway.app.store import SpecRegistryError, TaskStore


class SpecRegistryConcurrencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "tasks.db"
        self.store = TaskStore(self.db_path)
        self.store.initialize()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_concurrent_claim_has_single_winner(self) -> None:
        winners: list[str] = []
        errors: list[str] = []
        lock = threading.Lock()

        def contender(actor: str) -> None:
            try:
                result = self.store.claim_spec(
                    spec_id="softos-central-spec-registry-and-claiming",
                    actor=actor,
                    source="test",
                    reason="race",
                    ttl_seconds=5,
                )
                with lock:
                    winners.append(str(result["assignee"]))
            except SpecRegistryError as exc:
                with lock:
                    errors.append(exc.code)

        threads = [threading.Thread(target=contender, args=(f"actor-{idx}",)) for idx in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(1, len(winners))
        self.assertEqual(7, len(errors))
        self.assertTrue(all(code == "SPEC_ALREADY_CLAIMED" for code in errors))

    def test_release_allows_new_claim(self) -> None:
        claimed = self.store.claim_spec(
            spec_id="softos-central-spec-registry-and-claiming",
            actor="alice",
            source="test",
            reason="initial",
            ttl_seconds=5,
        )
        self.store.release_spec(
            spec_id="softos-central-spec-registry-and-claiming",
            actor="alice",
            lock_token=str(claimed["lock_token"]),
            source="test",
            reason="handoff",
        )
        reclaimed = self.store.claim_spec(
            spec_id="softos-central-spec-registry-and-claiming",
            actor="bob",
            source="test",
            reason="next",
            ttl_seconds=5,
        )
        self.assertEqual("bob", reclaimed["assignee"])

    def test_heartbeat_extends_ttl_and_expiration_unlocks(self) -> None:
        claimed = self.store.claim_spec(
            spec_id="softos-central-spec-registry-and-claiming",
            actor="alice",
            source="test",
            reason="start",
            ttl_seconds=5,
        )
        time.sleep(3.0)
        self.store.heartbeat_spec(
            spec_id="softos-central-spec-registry-and-claiming",
            actor="alice",
            lock_token=str(claimed["lock_token"]),
            source="test",
            reason="keepalive",
            ttl_seconds=5,
        )
        time.sleep(3.0)
        with self.assertRaises(SpecRegistryError) as ctx:
            self.store.claim_spec(
                spec_id="softos-central-spec-registry-and-claiming",
                actor="bob",
                source="test",
                reason="too-early",
                ttl_seconds=5,
            )
        self.assertEqual("SPEC_ALREADY_CLAIMED", ctx.exception.code)

        time.sleep(3.0)
        reclaimed = self.store.claim_spec(
            spec_id="softos-central-spec-registry-and-claiming",
            actor="bob",
            source="test",
            reason="expired-now",
            ttl_seconds=5,
        )
        self.assertEqual("bob", reclaimed["assignee"])


if __name__ == "__main__":
    unittest.main()
