from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path

from flowctl.locks import SQLiteGlobalLockBackend
from flowctl.multiagent import SchedulerConfig, run_slice_scheduler


class GlobalLockSchedulerIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.backend = SQLiteGlobalLockBackend(Path(self._tmpdir.name) / "locks.db")
        self.backend.initialize()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _utc_now_factory(self):
        counter = {"value": 0}

        def _utc_now() -> str:
            counter["value"] += 1
            return f"2026-01-01T00:00:{counter['value']:02d}+00:00"

        return _utc_now

    def test_global_backend_serializes_cross_run_semantic_lock(self) -> None:
        running = {"value": 0, "max": 0}
        lock = threading.Lock()

        def _start(_slice_name: str) -> int:
            with lock:
                running["value"] += 1
                running["max"] = max(running["max"], running["value"])
            time.sleep(0.05)
            with lock:
                running["value"] -= 1
            return 0

        plan = {
            "slices": [
                {
                    "name": "shared",
                    "repo": "root",
                    "semantic_locks": ["db:migrations"],
                    "owned_targets": ["backend/db/migrations/001.sql"],
                    "owned_patterns": ["backend/db/migrations/**"],
                }
            ]
        }
        reports: list[dict[str, object]] = []

        def _run(run_id: str) -> None:
            reports.append(
                run_slice_scheduler(
                    feature_slug=f"feature-{run_id}",
                    plan_payload=plan,
                    start_slice_callable=_start,
                    utc_now=self._utc_now_factory(),
                    config=SchedulerConfig(
                        max_workers=1,
                        per_repo_capacity=1,
                        per_hot_area_capacity=1,
                        lock_ttl_seconds=60,
                        max_retries_execution=0,
                    ),
                    lock_backend=self.backend,
                    owner_run_id=run_id,
                )
            )

        first = threading.Thread(target=_run, args=("run-1",))
        second = threading.Thread(target=_run, args=("run-2",))
        first.start()
        second.start()
        first.join()
        second.join()

        self.assertEqual(1, running["max"])
        self.assertEqual(2, len(reports))
        self.assertTrue(any(item["reason"].startswith("wait-global-lock:semantic:db:migrations") for report in reports for item in report["waits"]))

    def test_hot_area_lock_applies_when_no_semantic_lock_declared(self) -> None:
        running = {"value": 0, "max": 0}
        lock = threading.Lock()

        def _start(_slice_name: str) -> int:
            with lock:
                running["value"] += 1
                running["max"] = max(running["max"], running["value"])
            time.sleep(0.05)
            with lock:
                running["value"] -= 1
            return 0

        plan = {
            "slices": [
                {
                    "name": "shared",
                    "repo": "root",
                    "hot_area": "flowctl/workflows",
                    "owned_targets": ["flowctl/workflows.py"],
                    "owned_patterns": ["flowctl/workflows.py"],
                }
            ]
        }
        reports: list[dict[str, object]] = []

        def _run(run_id: str) -> None:
            reports.append(
                run_slice_scheduler(
                    feature_slug=f"feature-{run_id}",
                    plan_payload=plan,
                    start_slice_callable=_start,
                    utc_now=self._utc_now_factory(),
                    config=SchedulerConfig(
                        max_workers=1,
                        per_repo_capacity=1,
                        per_hot_area_capacity=1,
                        lock_ttl_seconds=60,
                        max_retries_execution=0,
                    ),
                    lock_backend=self.backend,
                    owner_run_id=run_id,
                )
            )

        first = threading.Thread(target=_run, args=("run-1",))
        second = threading.Thread(target=_run, args=("run-2",))
        first.start()
        second.start()
        first.join()
        second.join()

        self.assertEqual(1, running["max"])
        self.assertTrue(
            any(
                item["reason"].startswith("wait-global-lock:hot-area:root:flowctl/workflows")
                for report in reports
                for item in report["waits"]
            )
        )

    def test_repo_fallback_lock_applies_for_legacy_slice_without_hot_area(self) -> None:
        def _start(_slice_name: str) -> int:
            time.sleep(0.02)
            return 0

        plan = {
            "slices": [
                {
                    "name": "legacy",
                    "repo": "root",
                    "owned_targets": ["README.md"],
                    "owned_patterns": [],
                }
            ]
        }
        report = run_slice_scheduler(
            feature_slug="feature-legacy",
            plan_payload=plan,
            start_slice_callable=_start,
            utc_now=self._utc_now_factory(),
            config=SchedulerConfig(
                max_workers=1,
                per_repo_capacity=1,
                per_hot_area_capacity=1,
                lock_ttl_seconds=60,
                max_retries_execution=0,
            ),
            lock_backend=self.backend,
            owner_run_id="run-legacy",
        )
        self.assertEqual("passed", report["status"])
        lock_events = report["lock_events"]
        self.assertTrue(any(item["lock"] == "repo:root" for item in lock_events))


if __name__ == "__main__":
    unittest.main()
