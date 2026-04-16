from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from flowctl import workflows


class WorkflowEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state_store: dict[str, dict[str, object]] = {}
        self.now_counter = 0
        self._tmpdir = tempfile.TemporaryDirectory()
        self.workflow_report_root = Path(self._tmpdir.name)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _now(self) -> str:
        self.now_counter += 1
        return f"2026-01-01T00:00:{self.now_counter:02d}+00:00"

    def _read_state(self, slug: str) -> dict[str, object]:
        return dict(self.state_store.get(slug, {}))

    def _write_state(self, slug: str, payload: dict[str, object]) -> None:
        self.state_store[slug] = dict(payload)

    def _args(self, **overrides: object):  # noqa: ANN001
        base = {
            "spec": "softos-autonomous-sdlc-execution-engine",
            "resume_from_stage": "",
            "retry_stage": "",
            "pause_at_stage": "",
            "human_gated": False,
            "json": True,
            "orchestrator": "bmad",
            "force_orchestrator": False,
        }
        base.update(overrides)
        return type("Args", (), base)()

    def _callable_ok(self, output_payload: dict[str, object] | None = None):
        def _run(_args: object) -> int:
            if output_payload is not None:
                print(json.dumps(output_payload, indent=2, ensure_ascii=True))
            return 0

        return _run

    def test_human_gated_run_pauses_on_policy_block(self) -> None:
        slug = "softos-autonomous-sdlc-execution-engine"

        def _policy_block(**_kwargs: object) -> dict[str, object]:
            return {
                "stage": "plan",
                "allowed": False,
                "blocked_reasons": ["spec_approval:missing_approval"],
                "next_required_actions": ["python3 ./flow spec approve softos-autonomous-sdlc-execution-engine"],
            }

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = workflows.command_workflow_run(
                self._args(human_gated=True),
                require_dirs=lambda: None,
                workspace_config={"project": {"workflow": {"default_orchestrator": "bmad", "force_orchestrator": True}}},
                resolve_spec=lambda value: Path(value),
                spec_slug=lambda path: path.name,
                read_state=self._read_state,
                write_state=self._write_state,
                command_plan=self._callable_ok(),
                command_slice_start=self._callable_ok(),
                command_ci_spec=self._callable_ok(),
                command_ci_repo=self._callable_ok(),
                command_ci_integration=self._callable_ok(),
                command_release_promote=self._callable_ok(),
                command_release_verify=self._callable_ok(),
                command_infra_apply=self._callable_ok(),
                command_workflow_execute_feature=self._callable_ok(),
                command_drift_check=self._callable_ok(),
                command_contract_verify=self._callable_ok(),
                command_spec_generate_contracts=self._callable_ok(),
                plan_root=self.workflow_report_root,
                workflow_report_root=self.workflow_report_root,
                rel=lambda path: str(path),
                utc_now=self._now,
                json_dumps=lambda obj: json.dumps(obj, ensure_ascii=True),
                policy_check_callable=_policy_block,
            )

        self.assertEqual(0, rc)
        payload = json.loads(out.getvalue().strip())
        self.assertEqual("paused", payload["status"])
        self.assertEqual("paused", payload["engine_status"])
        self.assertEqual("plan", self.state_store[slug]["workflow_engine"]["paused_at_stage"])
        self.assertEqual("blocked", payload["stages"][0]["status"])
        self.assertEqual(["spec_approval:missing_approval"], payload["stages"][0]["human_gate"]["blocked_reasons"])
        self.assertEqual("idle", payload["rollback"]["status"])
        self.assertEqual([], payload["workflow_dlq"])

    def test_human_gated_resume_can_continue_after_policy_approval(self) -> None:
        slug = "softos-autonomous-sdlc-execution-engine"
        self.state_store[slug] = {
            "workflow_engine": {
                "status": "paused",
                "updated_at": self._now(),
                "paused_at_stage": "plan",
                "stages": {
                    "plan": {
                        "stage_name": "plan",
                        "status": "blocked",
                        "attempt": 0,
                        "failure_reason": "human-gate-blocked",
                    }
                },
            }
        }

        def _policy_allow(**_kwargs: object) -> dict[str, object]:
            return {"allowed": True, "blocked_reasons": [], "next_required_actions": []}

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = workflows.command_workflow_run(
                self._args(human_gated=True, resume_from_stage="plan"),
                require_dirs=lambda: None,
                workspace_config={"project": {"workflow": {"default_orchestrator": "bmad", "force_orchestrator": True}}},
                resolve_spec=lambda value: Path(value),
                spec_slug=lambda path: path.name,
                read_state=self._read_state,
                write_state=self._write_state,
                command_plan=self._callable_ok(),
                command_slice_start=self._callable_ok(),
                command_ci_spec=self._callable_ok(),
                command_ci_repo=self._callable_ok(),
                command_ci_integration=self._callable_ok(),
                command_release_promote=self._callable_ok(),
                command_release_verify=self._callable_ok(),
                command_infra_apply=self._callable_ok(),
                command_workflow_execute_feature=self._callable_ok(),
                command_drift_check=self._callable_ok(),
                command_contract_verify=self._callable_ok(),
                command_spec_generate_contracts=self._callable_ok(),
                plan_root=self.workflow_report_root,
                workflow_report_root=self.workflow_report_root,
                rel=lambda path: str(path),
                utc_now=self._now,
                json_dumps=lambda obj: json.dumps(obj, ensure_ascii=True),
                policy_check_callable=_policy_allow,
            )

        self.assertEqual(0, rc)
        payload = json.loads(out.getvalue().strip())
        self.assertEqual("completed", payload["status"])
        self.assertEqual("completed", payload["engine_status"])

    def test_pause_then_resume_continues(self) -> None:
        slug = "softos-autonomous-sdlc-execution-engine"
        pause_args = type("PauseArgs", (), {"spec": slug, "stage": "ci_repo", "json": True})()
        with contextlib.redirect_stdout(io.StringIO()):
            workflows.command_workflow_pause(
                pause_args,
                resolve_spec=lambda value: Path(value),
                spec_slug=lambda path: path.name,
                read_state=self._read_state,
                write_state=self._write_state,
                utc_now=self._now,
                json_dumps=lambda obj: json.dumps(obj, ensure_ascii=True),
            )

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = workflows.command_workflow_run(
                self._args(resume_from_stage="ci_repo"),
                require_dirs=lambda: None,
                workspace_config={"project": {"workflow": {"default_orchestrator": "bmad", "force_orchestrator": True}}},
                resolve_spec=lambda value: Path(value),
                spec_slug=lambda path: path.name,
                read_state=self._read_state,
                write_state=self._write_state,
                command_plan=self._callable_ok(),
                command_slice_start=self._callable_ok(),
                command_ci_spec=self._callable_ok(),
                command_ci_repo=self._callable_ok(),
                command_ci_integration=self._callable_ok(),
                command_release_promote=self._callable_ok(),
                command_release_verify=self._callable_ok(),
                command_infra_apply=self._callable_ok(),
                command_workflow_execute_feature=self._callable_ok(),
                command_drift_check=self._callable_ok(),
                command_contract_verify=self._callable_ok(),
                command_spec_generate_contracts=self._callable_ok(),
                plan_root=self.workflow_report_root,
                workflow_report_root=self.workflow_report_root,
                rel=lambda path: str(path),
                utc_now=self._now,
                json_dumps=lambda obj: json.dumps(obj, ensure_ascii=True),
            )
        self.assertEqual(0, rc)
        payload = json.loads(out.getvalue().strip())
        self.assertEqual("completed", payload["status"])
        self.assertNotEqual("paused", payload["engine_status"])

    def test_retry_continues_after_target_stage(self) -> None:
        slug = "softos-autonomous-sdlc-execution-engine"
        self.state_store[slug] = {
            "workflow_engine": {
                "status": "failed",
                "updated_at": self._now(),
                "paused_at_stage": None,
                "stages": {
                    "plan": {
                        "stage_name": "plan",
                        "status": "passed",
                        "attempt": 1,
                        "started_at": self._now(),
                        "finished_at": self._now(),
                        "input_ref": "state",
                        "output_ref": "plan",
                        "failure_reason": None,
                    },
                    "slice_start": {
                        "stage_name": "slice_start",
                        "status": "passed",
                        "attempt": 1,
                        "started_at": self._now(),
                        "finished_at": self._now(),
                        "input_ref": "state",
                        "output_ref": "slice",
                        "failure_reason": None,
                    },
                    "ci_spec": {
                        "stage_name": "ci_spec",
                        "status": "failed",
                        "attempt": 1,
                        "started_at": self._now(),
                        "finished_at": self._now(),
                        "input_ref": "state",
                        "output_ref": "ci-spec",
                        "failure_reason": "old failure",
                    },
                },
            }
        }
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = workflows.command_workflow_run(
                self._args(retry_stage="ci_spec"),
                require_dirs=lambda: None,
                workspace_config={"project": {"workflow": {"default_orchestrator": "bmad", "force_orchestrator": True}}},
                resolve_spec=lambda value: Path(value),
                spec_slug=lambda path: path.name,
                read_state=self._read_state,
                write_state=self._write_state,
                command_plan=self._callable_ok(),
                command_slice_start=self._callable_ok(),
                command_ci_spec=self._callable_ok(),
                command_ci_repo=self._callable_ok(),
                command_ci_integration=self._callable_ok(),
                command_release_promote=self._callable_ok(),
                command_release_verify=self._callable_ok(),
                command_infra_apply=self._callable_ok(),
                command_workflow_execute_feature=self._callable_ok(),
                command_drift_check=self._callable_ok(),
                command_contract_verify=self._callable_ok(),
                command_spec_generate_contracts=self._callable_ok(),
                plan_root=self.workflow_report_root,
                workflow_report_root=self.workflow_report_root,
                rel=lambda path: str(path),
                utc_now=self._now,
                json_dumps=lambda obj: json.dumps(obj, ensure_ascii=True),
            )
        self.assertEqual(0, rc)
        state = self.state_store[slug]
        engine = state["workflow_engine"]
        self.assertEqual("passed", engine["stages"]["ci_spec"]["status"])
        self.assertIn("ci_repo", engine["stages"])
        self.assertIn("ci_integration", engine["stages"])

    def test_output_ref_is_not_corrupted(self) -> None:
        def _ci_repo(_args: object) -> int:
            print(
                json.dumps(
                    {"reports": [], "json_report": ".flow/reports/ci/repo-all.json", "markdown_report": ".flow/reports/ci/repo-all.md"},
                    indent=2,
                    ensure_ascii=True,
                )
            )
            return 0

        rc, output_ref = workflows._run_stage_callable(
            "ci_repo",
            "softos-autonomous-sdlc-execution-engine",
            {
                "plan": self._callable_ok(),
                "slice_start": self._callable_ok(),
                "ci_spec": self._callable_ok(),
                "ci_repo": _ci_repo,
                "ci_integration": self._callable_ok(),
                "release_promote": self._callable_ok(),
                "release_verify": self._callable_ok(),
                "infra_apply": self._callable_ok(),
                "execute_feature": self._callable_ok(),
            },
        )
        self.assertEqual(0, rc)
        self.assertEqual(".flow/reports/ci/repo-all.json", output_ref)
        self.assertNotEqual("}", output_ref)

    def test_failure_stops_engine_and_marks_failed(self) -> None:
        def _ci_repo_fail(_args: object) -> int:
            return 1

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = workflows.command_workflow_run(
                self._args(),
                require_dirs=lambda: None,
                workspace_config={
                    "project": {
                        "workflow": {
                            "default_orchestrator": "bmad",
                            "force_orchestrator": True,
                            # Desactiva auto-retry para que la semantica original del test se mantenga.
                            "retry_policy": {
                                "infra": {"max_attempts": 0},
                                "dependencia": {"max_attempts": 0},
                                "validacion": {"max_attempts": 0},
                                "logica": {"max_attempts": 0},
                            },
                        }
                    }
                },
                resolve_spec=lambda value: Path(value),
                spec_slug=lambda path: path.name,
                read_state=self._read_state,
                write_state=self._write_state,
                command_plan=self._callable_ok(),
                command_slice_start=self._callable_ok(),
                command_ci_spec=self._callable_ok(),
                command_ci_repo=_ci_repo_fail,
                command_ci_integration=self._callable_ok(),
                command_release_promote=self._callable_ok(),
                command_release_verify=self._callable_ok(),
                command_infra_apply=self._callable_ok(),
                command_workflow_execute_feature=self._callable_ok(),
                command_drift_check=self._callable_ok(),
                command_contract_verify=self._callable_ok(),
                command_spec_generate_contracts=self._callable_ok(),
                plan_root=self.workflow_report_root,
                workflow_report_root=self.workflow_report_root,
                rel=lambda path: str(path),
                utc_now=self._now,
                json_dumps=lambda obj: json.dumps(obj, ensure_ascii=True),
            )
        self.assertEqual(1, rc)
        payload = json.loads(out.getvalue().strip())
        self.assertEqual("failed", payload["status"])
        stage_names = [item["stage_name"] for item in payload["stages"]]
        self.assertIn("ci_repo", stage_names)
        self.assertNotIn("ci_integration", stage_names)

    def test_backoff_and_jitter_applied_between_retries(self) -> None:
        sleep_calls: list[float] = []

        attempts = {"ci_repo": 0}

        def _ci_repo_maybe_recover(_args: object) -> int:
            attempts["ci_repo"] += 1
            return 1 if attempts["ci_repo"] == 1 else 0

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = workflows.command_workflow_run(
                self._args(),
                require_dirs=lambda: None,
                workspace_config={
                    "project": {
                        "workflow": {
                            "default_orchestrator": "bmad",
                            "force_orchestrator": True,
                            "retry_policy": {
                                "dependencia": {"max_attempts": 2, "backoff_seconds": 1, "jitter_seconds": 2},
                            },
                        }
                    }
                },
                resolve_spec=lambda value: Path(value),
                spec_slug=lambda path: path.name,
                read_state=self._read_state,
                write_state=self._write_state,
                command_plan=self._callable_ok(),
                command_slice_start=self._callable_ok(),
                command_ci_spec=self._callable_ok(),
                command_ci_repo=_ci_repo_maybe_recover,
                command_ci_integration=self._callable_ok(),
                command_release_promote=self._callable_ok(),
                command_release_verify=self._callable_ok(),
                command_infra_apply=self._callable_ok(),
                command_workflow_execute_feature=self._callable_ok(),
                command_drift_check=self._callable_ok(),
                command_contract_verify=self._callable_ok(),
                command_spec_generate_contracts=self._callable_ok(),
                plan_root=self.workflow_report_root,
                workflow_report_root=self.workflow_report_root,
                rel=lambda path: str(path),
                utc_now=self._now,
                json_dumps=lambda obj: json.dumps(obj, ensure_ascii=True),
                sleep_fn=lambda seconds: sleep_calls.append(seconds),
            )
        self.assertEqual(0, rc)
        self.assertEqual(2, attempts["ci_repo"])
        # Un solo reintento -> una sola llamada a sleep, sin jitter (attempt=2 => effective_jitter=min(2,1)=1).
        self.assertEqual(1 + 1, int(sleep_calls[0]))

    def test_retry_policy_applied_by_error_class(self) -> None:
        slug = "softos-autonomous-sdlc-execution-engine"
        attempts = {"ci_repo": 0}

        def _ci_repo_maybe_recover(_args: object) -> int:
            attempts["ci_repo"] += 1
            # Primer intento falla, segundo pasa.
            return 1 if attempts["ci_repo"] == 1 else 0

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = workflows.command_workflow_run(
                self._args(),
                require_dirs=lambda: None,
                workspace_config={
                    "project": {
                        "workflow": {
                            "default_orchestrator": "bmad",
                            "force_orchestrator": True,
                            "retry_policy": {
                                # dependencia -> permitir al menos 2 intentos
                                "dependencia": {"max_attempts": 2},
                            },
                        }
                    }
                },
                resolve_spec=lambda value: Path(value),
                spec_slug=lambda path: path.name,
                read_state=self._read_state,
                write_state=self._write_state,
                command_plan=self._callable_ok(),
                command_slice_start=self._callable_ok(),
                command_ci_spec=self._callable_ok(),
                command_ci_repo=_ci_repo_maybe_recover,
                command_ci_integration=self._callable_ok(),
                command_release_promote=self._callable_ok(),
                command_release_verify=self._callable_ok(),
                command_infra_apply=self._callable_ok(),
                command_workflow_execute_feature=self._callable_ok(),
                command_drift_check=self._callable_ok(),
                command_contract_verify=self._callable_ok(),
                command_spec_generate_contracts=self._callable_ok(),
                plan_root=self.workflow_report_root,
                workflow_report_root=self.workflow_report_root,
                rel=lambda path: str(path),
                utc_now=self._now,
                json_dumps=lambda obj: json.dumps(obj, ensure_ascii=True),
            )
        self.assertEqual(0, rc)
        self.assertEqual(2, attempts["ci_repo"])
        state = self.state_store[slug]
        engine = state["workflow_engine"]
        self.assertEqual("passed", engine["stages"]["ci_repo"]["status"])

    def test_rollback_complete_and_reassignment_ready(self) -> None:
        slug = "softos-autonomous-sdlc-execution-engine"
        # Simular plan y scheduler sin DLQ.
        plan_path = self.workflow_report_root / f"{slug}.json"
        plan_path.write_text(json.dumps({"slices": []}, ensure_ascii=True), encoding="utf-8")
        scheduler_path = self.workflow_report_root / f"{slug}-scheduler.json"
        scheduler_path.write_text(
            json.dumps({"status": "passed", "queue_size": 0, "capacity": {}, "jobs": [], "waits": [], "locks": [], "lock_events": [], "dlq": []}, ensure_ascii=True),
            encoding="utf-8",
        )

        def _ci_repo_fail(_args: object) -> int:
            return 1

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = workflows.command_workflow_run(
                self._args(),
                require_dirs=lambda: None,
                workspace_config={
                    "project": {
                        "workflow": {
                            "default_orchestrator": "bmad",
                            "force_orchestrator": True,
                            "retry_policy": {
                                "dependencia": {"max_attempts": 1},
                            },
                        }
                    }
                },
                resolve_spec=lambda value: Path(value),
                spec_slug=lambda path: path.name,
                read_state=self._read_state,
                write_state=self._write_state,
                command_plan=self._callable_ok(),
                command_slice_start=self._callable_ok(),
                command_ci_spec=self._callable_ok(),
                command_ci_repo=_ci_repo_fail,
                command_ci_integration=self._callable_ok(),
                command_release_promote=self._callable_ok(),
                command_release_verify=self._callable_ok(),
                command_infra_apply=self._callable_ok(),
                command_workflow_execute_feature=self._callable_ok(),
                command_drift_check=self._callable_ok(),
                command_contract_verify=self._callable_ok(),
                command_spec_generate_contracts=self._callable_ok(),
                plan_root=self.workflow_report_root,
                workflow_report_root=self.workflow_report_root,
                rel=lambda path: str(path),
                utc_now=self._now,
                json_dumps=lambda obj: json.dumps(obj, ensure_ascii=True),
            )
        self.assertEqual(1, rc)
        payload = json.loads(out.getvalue().strip())
        rollback = payload["rollback"]
        self.assertIn("summary", rollback)
        self.assertIn("stages", rollback)
        self.assertIn("reverted_items", rollback)
        self.assertIn("pending_items", rollback)
        self.assertIn("manual_actions_required", rollback)
        self.assertFalse(payload["reassignment_ready"])

    def test_rollback_partial_and_not_reassignment_ready(self) -> None:
        slug = "softos-autonomous-sdlc-execution-engine"
        scheduler_path = self.workflow_report_root / f"{slug}-scheduler.json"
        scheduler_path.write_text(
            json.dumps(
                {
                    "status": "failed",
                    "queue_size": 1,
                    "capacity": {},
                    "jobs": [],
                    "waits": [],
                    "locks": [],
                    "lock_events": [],
                    "dlq": [{"slice": "bad", "reason": "execution-failed:1", "attempt": 2}],
                },
                ensure_ascii=True,
            ),
            encoding="utf-8",
        )

        def _ci_repo_fail(_args: object) -> int:
            return 1

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = workflows.command_workflow_run(
                self._args(),
                require_dirs=lambda: None,
                workspace_config={
                    "project": {
                        "workflow": {
                            "default_orchestrator": "bmad",
                            "force_orchestrator": True,
                            "retry_policy": {
                                "dependencia": {"max_attempts": 1},
                            },
                        }
                    }
                },
                resolve_spec=lambda value: Path(value),
                spec_slug=lambda path: path.name,
                read_state=self._read_state,
                write_state=self._write_state,
                command_plan=self._callable_ok(),
                command_slice_start=self._callable_ok(),
                command_ci_spec=self._callable_ok(),
                command_ci_repo=_ci_repo_fail,
                command_ci_integration=self._callable_ok(),
                command_release_promote=self._callable_ok(),
                command_release_verify=self._callable_ok(),
                command_infra_apply=self._callable_ok(),
                command_workflow_execute_feature=self._callable_ok(),
                command_drift_check=self._callable_ok(),
                command_contract_verify=self._callable_ok(),
                command_spec_generate_contracts=self._callable_ok(),
                plan_root=self.workflow_report_root,
                workflow_report_root=self.workflow_report_root,
                rel=lambda path: str(path),
                utc_now=self._now,
                json_dumps=lambda obj: json.dumps(obj, ensure_ascii=True),
            )
        self.assertEqual(1, rc)
        payload = json.loads(out.getvalue().strip())
        rollback = payload["rollback"]
        self.assertEqual("partial", rollback["status"])
        self.assertFalse(payload["reassignment_ready"])
        self.assertIn("reassignment_reason", payload)

    def test_reassignment_ready_true_when_rollback_safe(self) -> None:
        engine = {
            "status": "failed",
            "rollback": {
                "status": "completed",
                "pending_items": [],
            },
        }
        ready, reason = workflows._compute_reassignment_state(
            engine=engine,
            workflow_dlq=[],
            scheduler_report={"jobs": []},
        )
        self.assertTrue(ready)
        self.assertEqual("", reason)

    def test_completed_run_reports_neutral_rollback(self) -> None:
        # Simula una corrida fallida previa con rollback y luego una corrida exitosa.
        slug = "softos-autonomous-sdlc-execution-engine"
        self.state_store[slug] = {
            "workflow_engine": {
                "status": "failed",
                "updated_at": self._now(),
                "paused_at_stage": None,
                "stages": {},
                "rollback": {
                    "status": "completed",
                    "updated_at": self._now(),
                    "stages": {"ci_repo": {"stage_name": "ci_repo", "status": "completed"}},
                    "reverted_items": [{"stage": "ci_repo", "action": "something"}],
                    "pending_items": [],
                    "manual_actions_required": False,
                    "summary": "some-rollback",
                },
            }
        }

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = workflows.command_workflow_run(
                self._args(),
                require_dirs=lambda: None,
                workspace_config={"project": {"workflow": {"default_orchestrator": "bmad", "force_orchestrator": True}}},
                resolve_spec=lambda value: Path(value),
                spec_slug=lambda path: path.name,
                read_state=self._read_state,
                write_state=self._write_state,
                command_plan=self._callable_ok(),
                command_slice_start=self._callable_ok(),
                command_ci_spec=self._callable_ok(),
                command_ci_repo=self._callable_ok(),
                command_ci_integration=self._callable_ok(),
                command_release_promote=self._callable_ok(),
                command_release_verify=self._callable_ok(),
                command_infra_apply=self._callable_ok(),
                command_workflow_execute_feature=self._callable_ok(),
                command_drift_check=self._callable_ok(),
                command_contract_verify=self._callable_ok(),
                command_spec_generate_contracts=self._callable_ok(),
                plan_root=self.workflow_report_root,
                workflow_report_root=self.workflow_report_root,
                rel=lambda path: str(path),
                utc_now=self._now,
                json_dumps=lambda obj: json.dumps(obj, ensure_ascii=True),
            )
        self.assertEqual(0, rc)
        payload = json.loads(out.getvalue().strip())
        rb = payload["rollback"]
        self.assertEqual("idle", rb["status"])
        self.assertEqual([], rb["reverted_items"])
        self.assertEqual([], rb["pending_items"])

    def test_workflow_run_generates_run_id_and_passes_it_to_scheduler(self) -> None:
        slug = "softos-autonomous-sdlc-execution-engine"
        plan_path = self.workflow_report_root / f"{slug}.json"
        plan_path.write_text(json.dumps({"slices": []}, ensure_ascii=True), encoding="utf-8")
        captured: dict[str, object] = {}

        def _scheduler(**kwargs: object) -> dict[str, object]:
            captured.update(kwargs)
            return {
                "status": "passed",
                "queue_size": 0,
                "capacity": {"max_workers": 1, "per_repo_capacity": 1, "per_hot_area_capacity": 1},
                "jobs": [],
                "waits": [],
                "locks": [],
                "lock_events": [],
                "dlq": [],
                "traceability": [],
            }

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = workflows.command_workflow_run(
                self._args(),
                require_dirs=lambda: None,
                workspace_config={"project": {"workflow": {"default_orchestrator": "bmad", "force_orchestrator": True}}},
                resolve_spec=lambda value: Path(value),
                spec_slug=lambda path: path.name,
                read_state=self._read_state,
                write_state=self._write_state,
                command_plan=self._callable_ok(),
                command_slice_start=self._callable_ok(),
                command_ci_spec=self._callable_ok(),
                command_ci_repo=self._callable_ok(),
                command_ci_integration=self._callable_ok(),
                command_release_promote=self._callable_ok(),
                command_release_verify=self._callable_ok(),
                command_infra_apply=self._callable_ok(),
                command_workflow_execute_feature=self._callable_ok(),
                command_drift_check=self._callable_ok(),
                command_contract_verify=self._callable_ok(),
                command_spec_generate_contracts=self._callable_ok(),
                plan_root=self.workflow_report_root,
                workflow_report_root=self.workflow_report_root,
                rel=lambda path: str(path),
                utc_now=self._now,
                json_dumps=lambda obj: json.dumps(obj, ensure_ascii=True),
                run_slice_scheduler_callable=_scheduler,
                lock_backend_factory=lambda: object(),
            )
        self.assertEqual(0, rc)
        payload = json.loads(out.getvalue().strip())
        self.assertTrue(str(payload["run_id"]).strip())
        self.assertEqual(payload["run_id"], self.state_store[slug]["workflow_engine"]["run_id"])
        self.assertEqual(payload["run_id"], captured["owner_run_id"])
        self.assertIsNotNone(captured["lock_backend"])

    def test_retry_stage_reuses_existing_run_id(self) -> None:
        slug = "softos-autonomous-sdlc-execution-engine"
        existing_run_id = "softos-autonomous-sdlc-execution-engine-existing123"
        self.state_store[slug] = {
            "workflow_engine": {
                "status": "failed",
                "run_id": existing_run_id,
                "run_started_at": self._now(),
                "updated_at": self._now(),
                "paused_at_stage": None,
                "stages": {
                    "plan": {
                        "stage_name": "plan",
                        "status": "passed",
                        "attempt": 1,
                        "started_at": self._now(),
                        "finished_at": self._now(),
                        "input_ref": "state",
                        "output_ref": "plan",
                        "failure_reason": None,
                    }
                },
            }
        }
        captured: dict[str, object] = {}

        def _scheduler(**kwargs: object) -> dict[str, object]:
            captured.update(kwargs)
            return {
                "status": "passed",
                "queue_size": 0,
                "capacity": {"max_workers": 1, "per_repo_capacity": 1, "per_hot_area_capacity": 1},
                "jobs": [],
                "waits": [],
                "locks": [],
                "lock_events": [],
                "dlq": [],
                "traceability": [],
            }

        plan_path = self.workflow_report_root / f"{slug}.json"
        plan_path.write_text(json.dumps({"slices": []}, ensure_ascii=True), encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = workflows.command_workflow_run(
                self._args(retry_stage="slice_start"),
                require_dirs=lambda: None,
                workspace_config={"project": {"workflow": {"default_orchestrator": "bmad", "force_orchestrator": True}}},
                resolve_spec=lambda value: Path(value),
                spec_slug=lambda path: path.name,
                read_state=self._read_state,
                write_state=self._write_state,
                command_plan=self._callable_ok(),
                command_slice_start=self._callable_ok(),
                command_ci_spec=self._callable_ok(),
                command_ci_repo=self._callable_ok(),
                command_ci_integration=self._callable_ok(),
                command_release_promote=self._callable_ok(),
                command_release_verify=self._callable_ok(),
                command_infra_apply=self._callable_ok(),
                command_workflow_execute_feature=self._callable_ok(),
                command_drift_check=self._callable_ok(),
                command_contract_verify=self._callable_ok(),
                command_spec_generate_contracts=self._callable_ok(),
                plan_root=self.workflow_report_root,
                workflow_report_root=self.workflow_report_root,
                rel=lambda path: str(path),
                utc_now=self._now,
                json_dumps=lambda obj: json.dumps(obj, ensure_ascii=True),
                run_slice_scheduler_callable=_scheduler,
                lock_backend_factory=lambda: object(),
            )
        self.assertEqual(0, rc)
        payload = json.loads(out.getvalue().strip())
        self.assertEqual(existing_run_id, payload["run_id"])
        self.assertEqual(existing_run_id, captured["owner_run_id"])



if __name__ == "__main__":
    unittest.main()
