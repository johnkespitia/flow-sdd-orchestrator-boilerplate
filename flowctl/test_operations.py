from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from flowctl import operations


class OperationsMetricsTests(unittest.TestCase):
    def _now(self) -> str:
        return "2026-01-01T00:00:00+00:00"

    def test_collect_workflow_metrics_basic_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reports = root / ".flow" / "reports" / "workflows"
            reports.mkdir(parents=True, exist_ok=True)
            payload = {
                "status": "completed",
                "stages": [
                    {
                        "stage_name": "ci_spec",
                        "attempt": 1,
                        "started_at": "2026-01-01T00:00:00+00:00",
                        "finished_at": "2026-01-01T00:00:10+00:00",
                    }
                ],
                "workflow_dlq": [],
            }
            (reports / "demo-workflow-run.json").write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")

            metrics = operations.collect_workflow_metrics(root=root, utc_now=self._now)
            self.assertIn("throughput", metrics)
            self.assertIn("failure_rate", metrics)
            self.assertIn("stage_latency", metrics)
            self.assertIn("retries", metrics)
            self.assertIn("dlq_size", metrics)
            self.assertEqual(1, metrics["throughput"])
            self.assertEqual(0.0, metrics["failure_rate"])
            self.assertEqual(0, metrics["retries"])
            self.assertEqual(0, metrics["dlq_size"])
            latencies = metrics["stage_latency"]
            self.assertTrue(any(item["stage"] == "ci_spec" and int(item["avg_seconds"]) == 10 for item in latencies))

    def test_evaluate_sla_alerts_generates_alert_when_threshold_exceeded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reports = root / ".flow" / "reports" / "workflows"
            reports.mkdir(parents=True, exist_ok=True)
            payload = {
                "status": "completed",
                "stages": [
                    {
                        "stage_name": "ci_repo",
                        "attempt": 1,
                        "started_at": "2026-01-01T00:00:00+00:00",
                        "finished_at": "2026-01-01T00:20:00+00:00",
                    }
                ],
                "workflow_dlq": [],
            }
            (reports / "demo-workflow-run.json").write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
            alerts = operations.evaluate_sla_alerts(root=root, utc_now=self._now, thresholds={"ci_repo": 600.0})
            self.assertGreater(len(alerts["alerts"]), 0)

    def test_collect_gateway_sqlite_task_metrics_by_intent_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "gw.db"
            conn = sqlite3.connect(db)
            conn.execute(
                """
                CREATE TABLE tasks (
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
                )
                """
            )
            for i in range(3):
                conn.execute(
                    """
                    INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        f"t{i}",
                        "github",
                        "workflow.intake",
                        "{}",
                        "[]",
                        None,
                        "succeeded",
                        "",
                        "",
                        None,
                        0,
                        "2026-01-01T00:00:00+00:00",
                        None,
                        "2026-01-01T00:00:10+00:00",
                        "2026-01-01T00:00:10+00:00",
                    ),
                )
            conn.commit()
            conn.close()
            m = operations.collect_gateway_sqlite_task_metrics(db_path=db)
            self.assertTrue(m.get("available"))
            rows = m.get("by_intent_provider") or []
            self.assertTrue(any(r.get("source") == "github" and r.get("intent") == "workflow.intake" for r in rows))

    def test_evaluate_gateway_task_processing_sla_failure_rate_alert(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "gw.db"
            conn = sqlite3.connect(db)
            conn.execute(
                """
                CREATE TABLE tasks (
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
                )
                """
            )
            for i in range(4):
                conn.execute(
                    """
                    INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        f"f{i}",
                        "api",
                        "spec.approve",
                        "{}",
                        "[]",
                        None,
                        "failed",
                        "",
                        "",
                        None,
                        1,
                        "2026-01-01T00:00:00+00:00",
                        None,
                        "2026-01-01T00:00:01+00:00",
                        "2026-01-01T00:00:01+00:00",
                    ),
                )
            conn.commit()
            conn.close()
            out = operations.evaluate_gateway_task_processing_sla(
                db_path=db,
                utc_now=self._now,
                failure_rate_threshold=0.25,
            )
            kinds = {a.get("kind") for a in out.get("alerts", []) if isinstance(a, dict)}
            self.assertIn("gateway_failure_rate", kinds)


class OperationsDecisionLogTests(unittest.TestCase):
    def _now(self) -> str:
        return "2026-01-01T00:00:00+00:00"

    def test_append_and_read_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entry = operations.append_decision(
                root=root,
                actor_type="human",
                actor="alice",
                decision="pause-release",
                context="high error rate",
                impact_or_risk="medium",
                utc_now=self._now,
            )
            self.assertEqual("human", entry["actor_type"])
            items = operations.read_decisions(root=root, max_items=10)
            self.assertEqual(1, len(items))
            self.assertEqual("alice", items[0]["actor"])


class OperationsDashboardTests(unittest.TestCase):
    def _now(self) -> str:
        return "2026-01-01T00:00:00+00:00"

    def _write_state(self, root: Path, slug: str, *, status: str, repos: list[str], actor: str = "") -> None:
        state_root = root / ".flow" / "state"
        state_root.mkdir(parents=True, exist_ok=True)
        payload = {
            "feature": slug,
            "repos": repos,
            "workflow_engine": {
                "status": status,
                "updated_at": "2026-01-01T00:00:00+00:00",
                "paused_at_stage": None,
                "actor": actor,
                "stages": {},
            },
            "slice_results": {
                "root-main": {"repo": repos[0] if repos else "root"},
            },
        }
        (state_root / f"{slug}.json").write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")

    def test_collect_runs_dashboard_supports_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_state(root, "alpha-feature", status="completed", repos=["root"], actor="alice")
            self._write_state(root, "beta-feature", status="failed", repos=["backend"], actor="bob")

            dashboard = operations.collect_runs_dashboard_filtered(
                root=root,
                utc_now=self._now,
                spec="alpha",
                repo="root",
                actor="alice",
                status="completed",
            )
            runs = dashboard["runs"]
            self.assertEqual(1, len(runs))
            self.assertEqual("alpha-feature", runs[0]["feature"])
            self.assertEqual("alice", runs[0]["actor"])
            self.assertEqual("alpha", dashboard["filters"]["spec"])


if __name__ == "__main__":
    unittest.main()
