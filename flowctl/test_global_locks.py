from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from flowctl.locks import GlobalLockError, SQLiteGlobalLockBackend


class _Clock:
    def __init__(self, *values: str) -> None:
        self._values = list(values)
        self._index = 0
        self._lock = threading.Lock()

    def __call__(self) -> str:
        with self._lock:
            if self._index >= len(self._values):
                return self._values[-1]
            value = self._values[self._index]
            self._index += 1
            return value


class GlobalLockBackendTests(unittest.TestCase):
    def _backend(self, *times: str) -> SQLiteGlobalLockBackend:
        self._tmpdir = tempfile.TemporaryDirectory()
        database = Path(self._tmpdir.name) / "locks.db"
        backend = SQLiteGlobalLockBackend(database, utc_now_fn=_Clock(*times))
        backend.initialize()
        return backend

    def tearDown(self) -> None:
        tmpdir = getattr(self, "_tmpdir", None)
        if tmpdir is not None:
            tmpdir.cleanup()

    def test_acquire_and_release_lock(self) -> None:
        backend = self._backend("2026-01-01T00:00:00+00:00", "2026-01-01T00:00:05+00:00")
        acquired = backend.acquire(
            lock_name="hot-area:flowctl/locks",
            scope="hot_area",
            repo="root",
            owner_run_id="run-1",
            owner_feature="feature-a",
            owner_slice="slice-a",
            ttl_seconds=60,
        )
        self.assertTrue(acquired["granted"])
        self.assertEqual("acquired", acquired["status"])
        current = backend.get_lock("hot-area:flowctl/locks")
        self.assertIsNotNone(current)
        released = backend.release(
            lock_name="hot-area:flowctl/locks",
            owner_run_id="run-1",
            owner_feature="feature-a",
            owner_slice="slice-a",
        )
        self.assertTrue(released["released"])
        self.assertIsNone(backend.get_lock("hot-area:flowctl/locks"))

    def test_concurrent_acquire_has_single_winner(self) -> None:
        backend = self._backend("2026-01-01T00:00:00+00:00")
        results: list[dict[str, object]] = []
        gate = threading.Barrier(2)

        def _claim(run_id: str) -> None:
            gate.wait()
            results.append(
                backend.acquire(
                    lock_name="semantic:db:migrations",
                    scope="semantic",
                    repo="root",
                    owner_run_id=run_id,
                    owner_feature=f"feature-{run_id}",
                    owner_slice=f"slice-{run_id}",
                    ttl_seconds=60,
                )
            )

        first = threading.Thread(target=_claim, args=("run-1",))
        second = threading.Thread(target=_claim, args=("run-2",))
        first.start()
        second.start()
        first.join()
        second.join()

        granted = [item for item in results if bool(item["granted"])]
        denied = [item for item in results if not bool(item["granted"])]
        self.assertEqual(1, len(granted))
        self.assertEqual(1, len(denied))
        self.assertEqual("denied", denied[0]["status"])

    def test_heartbeat_extends_expiration(self) -> None:
        backend = self._backend(
            "2026-01-01T00:00:00+00:00",
            "2026-01-01T00:00:30+00:00",
        )
        acquired = backend.acquire(
            lock_name="repo:root",
            scope="repo",
            repo="root",
            owner_run_id="run-1",
            owner_feature="feature-a",
            owner_slice="slice-a",
            ttl_seconds=60,
        )
        heartbeat = backend.heartbeat(
            lock_name="repo:root",
            owner_run_id="run-1",
            owner_feature="feature-a",
            owner_slice="slice-a",
            ttl_seconds=120,
        )
        self.assertEqual("heartbeat", heartbeat["status"])
        self.assertNotEqual(acquired["expires_at"], heartbeat["expires_at"])

    def test_expire_stale_releases_lock_for_new_owner(self) -> None:
        backend = self._backend(
            "2026-01-01T00:00:00+00:00",
            "2026-01-01T00:01:05+00:00",
            "2026-01-01T00:01:10+00:00",
        )
        backend.acquire(
            lock_name="semantic:api:routes",
            scope="semantic",
            repo="root",
            owner_run_id="run-1",
            owner_feature="feature-a",
            owner_slice="slice-a",
            ttl_seconds=60,
        )
        expired = backend.expire_stale()
        self.assertEqual(1, len(expired))
        acquired = backend.acquire(
            lock_name="semantic:api:routes",
            scope="semantic",
            repo="root",
            owner_run_id="run-2",
            owner_feature="feature-b",
            owner_slice="slice-b",
            ttl_seconds=60,
        )
        self.assertTrue(acquired["granted"])
        self.assertEqual("run-2", acquired["owner_run_id"])

    def test_same_owner_reacquire_renews_lock(self) -> None:
        backend = self._backend(
            "2026-01-01T00:00:00+00:00",
            "2026-01-01T00:00:10+00:00",
        )
        first = backend.acquire(
            lock_name="hot-area:flowctl/workflows",
            scope="hot_area",
            repo="root",
            owner_run_id="run-1",
            owner_feature="feature-a",
            owner_slice="slice-a",
            ttl_seconds=60,
        )
        second = backend.acquire(
            lock_name="hot-area:flowctl/workflows",
            scope="hot_area",
            repo="root",
            owner_run_id="run-1",
            owner_feature="feature-a",
            owner_slice="slice-a",
            ttl_seconds=120,
        )
        self.assertEqual("renewed", second["status"])
        self.assertEqual(first["acquired_at"], second["acquired_at"])
        self.assertNotEqual(first["expires_at"], second["expires_at"])

    def test_release_by_non_owner_fails(self) -> None:
        backend = self._backend("2026-01-01T00:00:00+00:00")
        backend.acquire(
            lock_name="repo:root",
            scope="repo",
            repo="root",
            owner_run_id="run-1",
            owner_feature="feature-a",
            owner_slice="slice-a",
            ttl_seconds=60,
        )
        with self.assertRaises(GlobalLockError):
            backend.release(
                lock_name="repo:root",
                owner_run_id="run-2",
                owner_feature="feature-b",
                owner_slice="slice-b",
            )

    def test_events_capture_lifecycle(self) -> None:
        backend = self._backend(
            "2026-01-01T00:00:00+00:00",
            "2026-01-01T00:00:05+00:00",
            "2026-01-01T00:00:10+00:00",
            "2026-01-01T00:00:15+00:00",
        )
        backend.acquire(
            lock_name="semantic:contracts:schema",
            scope="semantic",
            repo="root",
            owner_run_id="run-1",
            owner_feature="feature-a",
            owner_slice="slice-a",
            ttl_seconds=60,
        )
        backend.acquire(
            lock_name="semantic:contracts:schema",
            scope="semantic",
            repo="root",
            owner_run_id="run-2",
            owner_feature="feature-b",
            owner_slice="slice-b",
            ttl_seconds=60,
        )
        backend.heartbeat(
            lock_name="semantic:contracts:schema",
            owner_run_id="run-1",
            owner_feature="feature-a",
            owner_slice="slice-a",
            ttl_seconds=60,
        )
        backend.release(
            lock_name="semantic:contracts:schema",
            owner_run_id="run-1",
            owner_feature="feature-a",
            owner_slice="slice-a",
        )
        events = backend.list_events()
        self.assertTrue(any(item["event_type"] == "acquire" for item in events))
        self.assertTrue(any(item["event_type"] == "denied" for item in events))
        self.assertTrue(any(item["event_type"] == "heartbeat" for item in events))
        self.assertTrue(any(item["event_type"] == "release" for item in events))


if __name__ == "__main__":
    unittest.main()
