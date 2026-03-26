from __future__ import annotations

import threading
import time
import unittest

from flowctl.multiagent import SchedulerConfig, run_slice_scheduler


class MultiagentSchedulerTests(unittest.TestCase):
    def _utc_now_factory(self):
        counter = {"value": 0}

        def _utc_now() -> str:
            counter["value"] += 1
            return f"2026-01-01T00:00:{counter['value']:02d}+00:00"

        return _utc_now

    def test_atomic_claim_no_duplicate_execution(self) -> None:
        started: list[str] = []
        lock = threading.Lock()

        def _start(slice_name: str) -> int:
            with lock:
                started.append(slice_name)
            time.sleep(0.01)
            return 0

        plan = {
            "slices": [
                {"name": "a", "repo": "r1", "owned_targets": ["x/a.py"], "owned_patterns": ["x/a.py"]},
                {"name": "b", "repo": "r1", "owned_targets": ["x/b.py"], "owned_patterns": ["x/b.py"]},
                {"name": "c", "repo": "r2", "owned_targets": ["x/c.py"], "owned_patterns": ["x/c.py"]},
            ]
        }
        report = run_slice_scheduler(
            feature_slug="f1",
            plan_payload=plan,
            start_slice_callable=_start,
            utc_now=self._utc_now_factory(),
            config=SchedulerConfig(
                max_workers=4,
                per_repo_capacity=2,
                per_hot_area_capacity=2,
                lock_ttl_seconds=60,
                max_retries_execution=0,
            ),
        )
        self.assertEqual("passed", report["status"])
        self.assertCountEqual(["a", "b", "c"], started)

    def test_dag_blocks_child_until_parent(self) -> None:
        execution_order: list[str] = []
        lock = threading.Lock()

        def _start(slice_name: str) -> int:
            with lock:
                execution_order.append(slice_name)
            time.sleep(0.01)
            return 0

        plan = {
            "slices": [
                {"name": "parent", "repo": "r1", "owned_targets": ["x/p.py"], "owned_patterns": ["x/p.py"]},
                {
                    "name": "child",
                    "repo": "r1",
                    "depends_on": ["parent"],
                    "owned_targets": ["x/c.py"],
                    "owned_patterns": ["x/c.py"],
                },
            ]
        }
        report = run_slice_scheduler(
            feature_slug="f2",
            plan_payload=plan,
            start_slice_callable=_start,
            utc_now=self._utc_now_factory(),
            config=SchedulerConfig(
                max_workers=2,
                per_repo_capacity=2,
                per_hot_area_capacity=2,
                lock_ttl_seconds=60,
                max_retries_execution=0,
            ),
        )
        self.assertEqual("passed", report["status"])
        self.assertLess(execution_order.index("parent"), execution_order.index("child"))

    def test_semantic_locks_prevent_unsafe_parallel(self) -> None:
        running = {"value": 0, "max": 0}
        lock = threading.Lock()

        def _start(_slice_name: str) -> int:
            with lock:
                running["value"] += 1
                running["max"] = max(running["max"], running["value"])
            time.sleep(0.02)
            with lock:
                running["value"] -= 1
            return 0

        plan = {
            "slices": [
                {
                    "name": "s1",
                    "repo": "r1",
                    "semantic_locks": ["db:migrations"],
                    "owned_targets": ["db/migrations/001.sql"],
                    "owned_patterns": ["db/migrations/**"],
                },
                {
                    "name": "s2",
                    "repo": "r2",
                    "semantic_locks": ["db:migrations"],
                    "owned_targets": ["db/migrations/002.sql"],
                    "owned_patterns": ["db/migrations/**"],
                },
            ]
        }
        report = run_slice_scheduler(
            feature_slug="f3",
            plan_payload=plan,
            start_slice_callable=_start,
            utc_now=self._utc_now_factory(),
            config=SchedulerConfig(
                max_workers=4,
                per_repo_capacity=2,
                per_hot_area_capacity=2,
                lock_ttl_seconds=60,
                max_retries_execution=0,
            ),
        )
        self.assertEqual("passed", report["status"])
        self.assertEqual(1, running["max"])
        self.assertTrue(any(item["reason"].startswith("semantic-lock:") for item in report["waits"]))

    def test_retry_exhaustion_goes_to_dlq(self) -> None:
        attempts = {"bad": 0}

        def _start(slice_name: str) -> int:
            if slice_name == "bad":
                attempts["bad"] += 1
                return 1
            return 0

        plan = {"slices": [{"name": "bad", "repo": "r1", "owned_targets": ["x/bad.py"], "owned_patterns": ["x/bad.py"]}]}
        report = run_slice_scheduler(
            feature_slug="f4",
            plan_payload=plan,
            start_slice_callable=_start,
            utc_now=self._utc_now_factory(),
            config=SchedulerConfig(
                max_workers=1,
                per_repo_capacity=1,
                per_hot_area_capacity=1,
                lock_ttl_seconds=60,
                max_retries_execution=1,
            ),
        )
        self.assertEqual("failed", report["status"])
        self.assertEqual(2, attempts["bad"])
        self.assertEqual(1, len(report["dlq"]))
        self.assertEqual("bad", report["dlq"][0]["slice"])

    def test_parent_failed_marks_child_terminal_without_hang(self) -> None:
        def _start(slice_name: str) -> int:
            if slice_name == "parent":
                return 1
            return 0

        plan = {
            "slices": [
                {"name": "parent", "repo": "r1", "owned_targets": ["x/p.py"], "owned_patterns": ["x/p.py"]},
                {
                    "name": "child",
                    "repo": "r1",
                    "depends_on": ["parent"],
                    "owned_targets": ["x/c.py"],
                    "owned_patterns": ["x/c.py"],
                },
            ]
        }
        report = run_slice_scheduler(
            feature_slug="f5",
            plan_payload=plan,
            start_slice_callable=_start,
            utc_now=self._utc_now_factory(),
            config=SchedulerConfig(
                max_workers=2,
                per_repo_capacity=2,
                per_hot_area_capacity=2,
                lock_ttl_seconds=60,
                max_retries_execution=0,
            ),
        )
        self.assertEqual("failed", report["status"])
        jobs = {item["slice"]: item for item in report["jobs"]}
        self.assertEqual("failed", jobs["parent"]["status"])
        self.assertEqual("blocked", jobs["child"]["status"])
        self.assertEqual("dependency-failed:parent", jobs["child"]["failure_reason"])

    def test_lock_ttl_no_stealing_during_long_running_owner(self) -> None:
        running = {"value": 0, "max": 0}
        lock = threading.Lock()

        def _start(_slice_name: str) -> int:
            with lock:
                running["value"] += 1
                running["max"] = max(running["max"], running["value"])
            time.sleep(0.08)
            with lock:
                running["value"] -= 1
            return 0

        plan = {
            "slices": [
                {
                    "name": "holder",
                    "repo": "r1",
                    "semantic_locks": ["api:routes"],
                    "owned_targets": ["backend/api/routes.py"],
                    "owned_patterns": ["backend/api/**"],
                },
                {
                    "name": "contender",
                    "repo": "r2",
                    "semantic_locks": ["api:routes"],
                    "owned_targets": ["frontend/api/routes.ts"],
                    "owned_patterns": ["frontend/api/**"],
                },
            ]
        }
        report = run_slice_scheduler(
            feature_slug="f6",
            plan_payload=plan,
            start_slice_callable=_start,
            utc_now=self._utc_now_factory(),
            config=SchedulerConfig(
                max_workers=2,
                per_repo_capacity=2,
                per_hot_area_capacity=2,
                lock_ttl_seconds=0,
                max_retries_execution=0,
            ),
        )
        self.assertEqual("passed", report["status"])
        self.assertEqual(1, running["max"])

    def test_lock_events_present_in_report(self) -> None:
        def _start(_slice_name: str) -> int:
            time.sleep(0.02)
            return 0

        plan = {
            "slices": [
                {
                    "name": "s1",
                    "repo": "r1",
                    "semantic_locks": ["contracts:schema"],
                    "owned_targets": ["contracts/api.yaml"],
                    "owned_patterns": ["contracts/**"],
                },
                {
                    "name": "s2",
                    "repo": "r2",
                    "semantic_locks": ["contracts:schema"],
                    "owned_targets": ["contracts/web.yaml"],
                    "owned_patterns": ["contracts/**"],
                },
            ]
        }
        report = run_slice_scheduler(
            feature_slug="f7",
            plan_payload=plan,
            start_slice_callable=_start,
            utc_now=self._utc_now_factory(),
            config=SchedulerConfig(
                max_workers=2,
                per_repo_capacity=2,
                per_hot_area_capacity=2,
                lock_ttl_seconds=60,
                max_retries_execution=0,
            ),
        )
        self.assertEqual("passed", report["status"])
        events = report.get("lock_events", [])
        self.assertTrue(any(item.get("event") == "acquire" for item in events))
        self.assertTrue(any(item.get("event") == "release" for item in events))
        self.assertTrue(any(item.get("event") == "denied" for item in events))


if __name__ == "__main__":
    unittest.main()
