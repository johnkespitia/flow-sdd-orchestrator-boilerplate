from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from gateway.app.config import Settings
from gateway.app.store import TaskStore
from gateway.app.worker import TaskWorker

try:
    from gateway.app.main import app
except Exception:  # pragma: no cover - runtime compatibility guard
    app = None


def _fake_run_flow_command(settings, command):  # noqa: ANN001
    if command[:2] == ["workflow", "intake"]:
        return {"command": command, "exit_code": 0, "stdout": '{"status":"draft-spec"}', "stderr": "", "parsed_output": {"status": "draft-spec"}}
    if command[:2] == ["spec", "approve"]:
        return {"command": command, "exit_code": 0, "stdout": '{"status":"approved"}', "stderr": "", "parsed_output": {"status": "approved"}}
    if command[:2] == ["workflow", "execute-feature"]:
        return {"command": command, "exit_code": 0, "stdout": '{"status":"closed"}', "stderr": "", "parsed_output": {"status": "closed"}}
    return {"command": command, "exit_code": 0, "stdout": "{}", "stderr": "", "parsed_output": {}}


def _fake_run_flow_command_fail_execute(settings, command):  # noqa: ANN001
    if command[:2] == ["workflow", "execute-feature"]:
        return {"command": command, "exit_code": 1, "stdout": '{"status":"failed"}', "stderr": "boom", "parsed_output": {"status": "failed"}}
    return _fake_run_flow_command(settings, command)


class GatewayIntakeCollaborationE2ETests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmpdir.name)
        db_path = self.workspace / "tasks.db"
        self.store = TaskStore(db_path)
        self.store.initialize()
        self.settings = Settings(
            workspace_root=self.workspace,
            database_path=db_path,
            flow_bin="python3",
            flow_entrypoint="./flow",
            gateway_api_token=None,
            slack_signing_secret=None,
            github_webhook_secret=None,
            jira_webhook_token=None,
            default_feedback_provider=None,
            worker_poll_interval=0.02,
        )

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _wait_done(self, task_id: str) -> dict:
        deadline = time.time() + 5.0
        while time.time() < deadline:
            task = self.store.get(task_id)
            if task["status"] in {"succeeded", "failed", "completed_with_findings"}:
                return task
            time.sleep(0.05)
        self.fail(f"Task {task_id} no finalizo a tiempo")

    def test_e2e_intake_claim_approve_execute_close(self) -> None:
        with (
            patch("gateway.app.worker.run_flow_command", side_effect=_fake_run_flow_command),
            patch("gateway.app.worker.send_feedback", return_value=None),
            patch("gateway.app.worker.send_feedback_event", return_value=None),
        ):
            worker = TaskWorker(self.settings, self.store)
            worker.start()
            try:
                intake = self.store.enqueue(
                    source="github",
                    intent="workflow.intake",
                    payload={"slug": "spec-7"},
                    command=["workflow", "intake", "spec-7", "--title", "Spec 7", "--repo", "sdd-workspace-boilerplate", "--json"],
                    response_target=None,
                )
                self.store.claim_spec(spec_id="spec-7", actor="dev-a", source="api", reason="take", ttl_seconds=30)
                approve = self.store.enqueue(
                    source="api",
                    intent="spec.approve",
                    payload={"slug": "spec-7"},
                    command=["spec", "approve", "spec-7"],
                    response_target=None,
                )
                execute = self.store.enqueue(
                    source="api",
                    intent="workflow.execute_feature",
                    payload={"slug": "spec-7"},
                    command=["workflow", "execute-feature", "spec-7", "--json"],
                    response_target=None,
                )

                _ = self._wait_done(intake["task_id"])
                approve_task = self._wait_done(approve["task_id"])
                execute_task = self._wait_done(execute["task_id"])
                intake_events = [item["event"] for item in self.store.get(intake["task_id"])["events"]]
                self.assertEqual(intake_events.count("created"), 1)
                self.assertNotIn("closed", intake_events)
                approve_events = [item["event"] for item in approve_task["events"]]
                self.assertNotIn("closed", approve_events)
                events = [item["event"] for item in execute_task["events"]]
                self.assertIn("execution_started", events)
                self.assertIn("execution_succeeded", events)
                self.assertIn("closed", events)
            finally:
                worker.stop()

    def test_e2e_execute_failure_emits_failed_not_closed(self) -> None:
        with (
            patch("gateway.app.worker.run_flow_command", side_effect=_fake_run_flow_command_fail_execute),
            patch("gateway.app.worker.send_feedback", return_value=None),
            patch("gateway.app.worker.send_feedback_event", return_value=None),
        ):
            worker = TaskWorker(self.settings, self.store)
            worker.start()
            try:
                task = self.store.enqueue(
                    source="api",
                    intent="workflow.execute_feature",
                    payload={"slug": "spec-7"},
                    command=["workflow", "execute-feature", "spec-7", "--json"],
                    response_target=None,
                )
                finished = self._wait_done(task["task_id"])
                events = [item["event"] for item in finished["events"]]
                self.assertIn("execution_started", events)
                self.assertIn("execution_failed", events)
                self.assertNotIn("closed", events)
                self.assertEqual("failed", finished["status"])
            finally:
                worker.stop()

    def test_task_comment_emits_comment_added_feedback(self) -> None:
        if app is None:
            self.skipTest("gateway.app.main no es importable en este runtime")
        with (
            patch("gateway.app.main.TaskWorker.start", return_value=None),
            patch("gateway.app.main.TaskWorker.stop", return_value=None),
            patch("gateway.app.main.send_feedback_event", return_value=None) as send_feedback_event_mock,
        ):
            with TestClient(app) as client:
                task = client.app.state.store.enqueue(
                    source="github",
                    intent="workflow.intake",
                    payload={"slug": "spec-7"},
                    command=["workflow", "intake", "spec-7", "--title", "Spec 7", "--repo", "sdd-workspace-boilerplate", "--json"],
                    response_target={
                        "kind": "github",
                        "provider": "github-comment",
                        "comments_url": "https://api.github.com/repos/o/r/issues/7/comments",
                    },
                )
                response = client.post(
                    f"/v1/tasks/{task['task_id']}/comments",
                    json={
                        "actor": "reporter-1",
                        "message": "please review",
                        "source": "github",
                        "direction": "reporter_to_dev",
                    },
                )
                assert response.status_code == 200
                body = response.json()
                assert body["task_id"] == task["task_id"]
                assert any(item["event"] == "comment_added" for item in body["events"])
                send_feedback_event_mock.assert_called_once()
                kwargs = send_feedback_event_mock.call_args.kwargs
                self.assertEqual("comment_added", kwargs["event"])
                self.assertEqual("github", kwargs["source"])
                self.assertEqual("queued", kwargs["status"])
                self.assertEqual(task["task_id"], kwargs["payload"]["task_id"])
                self.assertEqual("reporter-1", kwargs["payload"]["actor"])
                self.assertEqual("reporter_to_dev", kwargs["payload"]["direction"])
                self.assertEqual("please review", kwargs["payload"]["message"])


if __name__ == "__main__":
    unittest.main()
