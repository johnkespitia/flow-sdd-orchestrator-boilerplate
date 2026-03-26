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
                workspace_config={"project": {"workflow": {"default_orchestrator": "bmad", "force_orchestrator": True}}},
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


if __name__ == "__main__":
    unittest.main()
