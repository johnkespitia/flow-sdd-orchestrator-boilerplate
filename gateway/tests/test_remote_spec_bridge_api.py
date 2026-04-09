from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from gateway.app import config as gateway_config
from gateway.app.main import app


def _settings_loader(workspace_root: Path, db_path: Path):
    def _load() -> gateway_config.Settings:
        return gateway_config.Settings(
            workspace_root=workspace_root,
            database_path=db_path,
            flow_bin="python3",
            flow_entrypoint="./flow",
            gateway_api_token=None,
            slack_signing_secret=None,
            github_webhook_secret=None,
            jira_webhook_token=None,
            default_feedback_provider=None,
            worker_poll_interval=0.05,
        )

    return _load


class RemoteSpecBridgeApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmpdir.name) / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.db_path = self.workspace / "gateway" / "data" / "tasks.db"
        self.load = _settings_loader(self.workspace, self.db_path)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_get_spec_source_returns_canonical_markdown(self) -> None:
        spec_path = self.workspace / "specs" / "features" / "demo.spec.md"
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text("---\nstatus: draft\n---\n\n# Demo\n", encoding="utf-8")

        with (
            patch.object(gateway_config, "load_settings", self.load),
            patch("gateway.app.main.load_settings", self.load),
            patch("gateway.app.main.TaskWorker.start", return_value=None),
            patch("gateway.app.main.TaskWorker.stop", return_value=None),
        ):
            with TestClient(app) as client:
                response = client.get("/v1/specs/demo/source")
                self.assertEqual(200, response.status_code)
                body = response.json()
                self.assertEqual("demo", body["spec_id"])
                self.assertTrue(body["path"].endswith("specs/features/demo.spec.md"))
                self.assertIn("# Demo", body["content"])
                self.assertTrue(body["updated_at"])
                self.assertEqual(64, len(body["content_sha256"]))

    def test_reassign_rotates_lock_and_audits(self) -> None:
        (self.workspace / "specs" / "features").mkdir(parents=True, exist_ok=True)

        with (
            patch.object(gateway_config, "load_settings", self.load),
            patch("gateway.app.main.load_settings", self.load),
            patch("gateway.app.main.TaskWorker.start", return_value=None),
            patch("gateway.app.main.TaskWorker.stop", return_value=None),
        ):
            with TestClient(app) as client:
                claimed = client.post(
                    "/v1/specs/demo/claim",
                    json={"actor": "alice", "source": "slave", "reason": "take", "ttl_seconds": 120},
                )
                self.assertEqual(200, claimed.status_code)
                original_token = claimed.json()["lock_token"]

                reassigned = client.post(
                    "/v1/specs/demo/reassign",
                    json={
                        "actor": "alice",
                        "to_actor": "bob",
                        "lock_token": original_token,
                        "role": "coordinator",
                        "force": False,
                        "source": "slave",
                        "reason": "handoff to bob",
                        "ttl_seconds": 120,
                    },
                )
                self.assertEqual(200, reassigned.status_code)
                reassigned_body = reassigned.json()
                self.assertEqual("bob", reassigned_body["assignee"])
                self.assertNotEqual(original_token, reassigned_body["lock_token"])

                stale_heartbeat = client.post(
                    "/v1/specs/demo/heartbeat",
                    json={
                        "actor": "alice",
                        "lock_token": original_token,
                        "source": "slave",
                        "reason": "old token",
                        "ttl_seconds": 120,
                    },
                )
                self.assertEqual(409, stale_heartbeat.status_code)
                self.assertEqual("LOCK_MISMATCH", stale_heartbeat.json()["detail"]["code"])

                next_token = reassigned_body["lock_token"]
                fresh_heartbeat = client.post(
                    "/v1/specs/demo/heartbeat",
                    json={
                        "actor": "bob",
                        "lock_token": next_token,
                        "source": "slave",
                        "reason": "continue work",
                        "ttl_seconds": 120,
                    },
                )
                self.assertEqual(200, fresh_heartbeat.status_code)

                fetched = client.get("/v1/specs/demo")
                self.assertEqual(200, fetched.status_code)
                audit = fetched.json()["audit"]
                self.assertTrue(any(item["event"] == "reassign" for item in audit))
                self.assertTrue(any("handoff to bob" in item["reason"] for item in audit))

    def test_reassign_requires_authorized_role_and_reason(self) -> None:
        (self.workspace / "specs" / "features").mkdir(parents=True, exist_ok=True)

        with (
            patch.object(gateway_config, "load_settings", self.load),
            patch("gateway.app.main.load_settings", self.load),
            patch("gateway.app.main.TaskWorker.start", return_value=None),
            patch("gateway.app.main.TaskWorker.stop", return_value=None),
        ):
            with TestClient(app) as client:
                claimed = client.post(
                    "/v1/specs/demo/claim",
                    json={"actor": "alice", "source": "slave", "reason": "take", "ttl_seconds": 120},
                )
                self.assertEqual(200, claimed.status_code)
                original_token = claimed.json()["lock_token"]

                forbidden = client.post(
                    "/v1/specs/demo/reassign",
                    json={
                        "actor": "alice",
                        "to_actor": "bob",
                        "lock_token": original_token,
                        "role": "assignee",
                        "force": False,
                        "source": "slave",
                        "reason": "handoff",
                        "ttl_seconds": 120,
                    },
                )
                self.assertEqual(403, forbidden.status_code)
                self.assertEqual("REASSIGN_FORBIDDEN", forbidden.json()["detail"]["code"])

                force_forbidden = client.post(
                    "/v1/specs/demo/reassign",
                    json={
                        "actor": "alice",
                        "to_actor": "bob",
                        "lock_token": original_token,
                        "role": "coordinator",
                        "force": True,
                        "source": "slave",
                        "reason": "urgent handoff",
                        "ttl_seconds": 120,
                    },
                )
                self.assertEqual(403, force_forbidden.status_code)
                self.assertEqual("REASSIGN_FORCE_FORBIDDEN", force_forbidden.json()["detail"]["code"])

                missing_reason = client.post(
                    "/v1/specs/demo/reassign",
                    json={
                        "actor": "alice",
                        "to_actor": "bob",
                        "lock_token": original_token,
                        "role": "admin",
                        "force": True,
                        "source": "slave",
                        "reason": "",
                        "ttl_seconds": 120,
                    },
                )
                self.assertEqual(400, missing_reason.status_code)
                self.assertEqual("REASSIGN_REASON_REQUIRED", missing_reason.json()["detail"]["code"])


if __name__ == "__main__":
    unittest.main()
