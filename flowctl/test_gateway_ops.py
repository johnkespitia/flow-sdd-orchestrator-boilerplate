from __future__ import annotations

import argparse
import contextlib
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from flowctl import gateway_ops


class GatewayOpsTests(unittest.TestCase):
    @staticmethod
    def _json_dumps(payload: object) -> str:
        return json.dumps(payload, indent=2, ensure_ascii=True)

    def test_load_gateway_connection_prefers_env_gateway_file(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.gateway").write_text(
                "SOFTOS_GATEWAY_URL=https://gateway.example.internal\nSOFTOS_GATEWAY_API_TOKEN=secret-token\n",
                encoding="utf-8",
            )
            workspace_config = {"gateway": {"connection": {"mode": "remote", "base_url": "https://stale.example"}}}

            payload = gateway_ops.load_gateway_connection(root=root, workspace_config=workspace_config)

            self.assertEqual("remote", payload["mode"])
            self.assertEqual("https://gateway.example.internal", payload["base_url"])
            self.assertEqual("secret-token", payload["api_token"])

    def test_command_gateway_fetch_spec_materializes_remote_markdown(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_config = {"gateway": {"connection": {"mode": "remote", "base_url": "https://gateway.example"}}}
            state: dict[str, object] = {}

            def _http_json(**kwargs):  # type: ignore[no-untyped-def]
                self.assertEqual("https://gateway.example/v1/specs/demo/source", kwargs["url"])
                return {
                    "spec_id": "demo",
                    "path": "/workspace/specs/features/demo.spec.md",
                    "content": "---\nstatus: approved\n---\n\n# Demo\n",
                    "updated_at": "2026-04-09T00:00:00+00:00",
                    "content_sha256": "abc123",
                }

            original = gateway_ops._http_json
            gateway_ops._http_json = _http_json  # type: ignore[assignment]
            try:
                rc = gateway_ops.command_gateway_fetch_spec(
                    argparse.Namespace(spec="demo", json=False),
                    root=root,
                    workspace_config=workspace_config,
                    read_state=lambda _slug: dict(state),
                    write_state=lambda _slug, payload: state.update(payload),
                    json_dumps=self._json_dumps,
                )
            finally:
                gateway_ops._http_json = original  # type: ignore[assignment]

            self.assertEqual(0, rc)
            self.assertTrue((root / "specs" / "features" / "demo.spec.md").is_file())
            self.assertEqual("specs/features/demo.spec.md", state["spec_path"])

    def test_ensure_remote_claim_for_plan_rejects_missing_claim(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace_config = {"gateway": {"connection": {"mode": "remote", "base_url": "https://gateway.example"}}}
            with self.assertRaises(SystemExit) as ctx:
                gateway_ops.ensure_remote_claim_for_plan(
                    root=Path(tmp),
                    slug="demo",
                    read_state=lambda _slug: {},
                    workspace_config=workspace_config,
                )
            self.assertIn("claim remoto", str(ctx.exception))

    def test_command_gateway_heartbeat_uses_local_claim(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_config = {"gateway": {"connection": {"mode": "remote", "base_url": "https://gateway.example"}}}
            state = {
                "gateway_claim": {
                    "mode": "remote",
                    "base_url": "https://gateway.example",
                    "spec_id": "demo",
                    "actor": "dev-a",
                    "lock_token": "lock-1",
                }
            }

            def _http_json(**kwargs):  # type: ignore[no-untyped-def]
                self.assertEqual("POST", kwargs["method"])
                self.assertEqual("https://gateway.example/v1/specs/demo/heartbeat", kwargs["url"])
                self.assertEqual("dev-a", kwargs["payload"]["actor"])
                self.assertEqual("lock-1", kwargs["payload"]["lock_token"])
                return {"state": "claimed", "lock_expires_at": "2026-04-09T12:00:00+00:00"}

            original = gateway_ops._http_json
            gateway_ops._http_json = _http_json  # type: ignore[assignment]
            try:
                stream = io.StringIO()
                with contextlib.redirect_stdout(stream):
                    rc = gateway_ops.command_gateway_heartbeat(
                        argparse.Namespace(spec="demo", ttl_seconds=90, reason="", json=True),
                        root=root,
                        workspace_config=workspace_config,
                        read_state=lambda _slug: dict(state),
                        write_state=lambda _slug, payload: state.update(payload),
                        json_dumps=self._json_dumps,
                    )
            finally:
                gateway_ops._http_json = original  # type: ignore[assignment]

            self.assertEqual(0, rc)
            payload = json.loads(stream.getvalue())
            self.assertEqual("demo", payload["spec_id"])
            self.assertEqual("dev-a", payload["actor"])
            self.assertEqual("claimed", payload["state"])

    def test_command_gateway_release_clears_local_claim_state(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_config = {"gateway": {"connection": {"mode": "remote", "base_url": "https://gateway.example"}}}
            state = {
                "gateway_claim": {
                    "mode": "remote",
                    "base_url": "https://gateway.example",
                    "spec_id": "demo",
                    "actor": "dev-a",
                    "lock_token": "lock-1",
                }
            }

            def read_state(_slug: str) -> dict[str, object]:
                return dict(state)

            def write_state(_slug: str, payload: dict[str, object]) -> None:
                state.clear()
                state.update(payload)

            def _http_json(**kwargs):  # type: ignore[no-untyped-def]
                self.assertEqual("POST", kwargs["method"])
                self.assertEqual("https://gateway.example/v1/specs/demo/release", kwargs["url"])
                return {"state": "triaged", "assignee": None}

            original = gateway_ops._http_json
            gateway_ops._http_json = _http_json  # type: ignore[assignment]
            try:
                stream = io.StringIO()
                with contextlib.redirect_stdout(stream):
                    rc = gateway_ops.command_gateway_release(
                        argparse.Namespace(spec="demo", reason="", json=True),
                        root=root,
                        workspace_config=workspace_config,
                        read_state=read_state,
                        write_state=write_state,
                        json_dumps=self._json_dumps,
                    )
            finally:
                gateway_ops._http_json = original  # type: ignore[assignment]

            self.assertEqual(0, rc)
            self.assertNotIn("gateway_claim", state)
            payload = json.loads(stream.getvalue())
            self.assertEqual("demo", payload["spec_id"])
            self.assertEqual("triaged", payload["state"])

    def test_command_gateway_reassign_rotates_local_claim_actor(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_config = {"gateway": {"connection": {"mode": "remote", "base_url": "https://gateway.example"}}}
            state = {
                "gateway_claim": {
                    "mode": "remote",
                    "base_url": "https://gateway.example",
                    "spec_id": "demo",
                    "actor": "dev-a",
                    "lock_token": "lock-1",
                }
            }

            def read_state(_slug: str) -> dict[str, object]:
                return dict(state)

            def write_state(_slug: str, payload: dict[str, object]) -> None:
                state.clear()
                state.update(payload)

            def _http_json(**kwargs):  # type: ignore[no-untyped-def]
                self.assertEqual("POST", kwargs["method"])
                self.assertEqual("https://gateway.example/v1/specs/demo/reassign", kwargs["url"])
                self.assertEqual("dev-b", kwargs["payload"]["to_actor"])
                return {"state": "claimed", "assignee": "dev-b", "lock_token": "lock-2"}

            original = gateway_ops._http_json
            gateway_ops._http_json = _http_json  # type: ignore[assignment]
            try:
                stream = io.StringIO()
                with contextlib.redirect_stdout(stream):
                    rc = gateway_ops.command_gateway_reassign(
                        argparse.Namespace(spec="demo", to_actor="dev-b", ttl_seconds=120, reason="", json=True),
                        root=root,
                        workspace_config=workspace_config,
                        read_state=read_state,
                        write_state=write_state,
                        json_dumps=self._json_dumps,
                    )
            finally:
                gateway_ops._http_json = original  # type: ignore[assignment]

            self.assertEqual(0, rc)
            claim = state["gateway_claim"]
            self.assertEqual("dev-b", claim["actor"])
            self.assertEqual("lock-2", claim["lock_token"])
            payload = json.loads(stream.getvalue())
            self.assertEqual("dev-a", payload["from_actor"])
            self.assertEqual("dev-b", payload["to_actor"])


if __name__ == "__main__":
    unittest.main()
