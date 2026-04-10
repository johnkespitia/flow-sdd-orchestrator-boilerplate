from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from flowctl.features import command_plan
from flowctl.specs import analyze_spec, build_spec_config, require_routed_paths
from flowctl import gateway_ops


class GatewayOpsTests(unittest.TestCase):
    @staticmethod
    def _json_dumps(payload: object) -> str:
        return json.dumps(payload, indent=2, ensure_ascii=True)

    @staticmethod
    def _spec_config(root: Path):  # type: ignore[no-untyped-def]
        return build_spec_config(
            root=root,
            specs_root=root / "specs",
            feature_specs=root / "specs" / "features",
            root_repo="root",
            default_targets={"root": ["../../specs/**"], "api": ["../../api/app/**"]},
            repo_prefixes={"api": "../../api/", "root": "../../"},
            target_roots={"root": {"specs"}, "api": {"app"}},
            test_required_roots={"root": set(), "api": set()},
            test_hints={"api": "../../api/tests/**"},
            required_frontmatter_fields=("name", "description", "status", "targets"),
            test_ref_re=re.compile(r"\[@test\]\s+([^\s`]+)"),
            todo_re=re.compile(r"\bTODO\b"),
        )

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

    def test_command_gateway_status_reports_local_remote_match(self) -> None:
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
                self.assertEqual("GET", kwargs["method"])
                self.assertEqual("https://gateway.example/v1/specs/demo", kwargs["url"])
                return {
                    "spec_id": "demo",
                    "state": "triaged",
                    "assignee": "dev-a",
                    "lock_token": "lock-1",
                    "lock_expires_at": "2026-04-09T12:00:00+00:00",
                }

            original = gateway_ops._http_json
            gateway_ops._http_json = _http_json  # type: ignore[assignment]
            try:
                stream = io.StringIO()
                with contextlib.redirect_stdout(stream):
                    rc = gateway_ops.command_gateway_status(
                        argparse.Namespace(spec="demo", json=True),
                        root=root,
                        workspace_config=workspace_config,
                        read_state=lambda _slug: dict(state),
                        json_dumps=self._json_dumps,
                    )
            finally:
                gateway_ops._http_json = original  # type: ignore[assignment]

            self.assertEqual(0, rc)
            payload = json.loads(stream.getvalue())
            self.assertTrue(payload["has_local_claim"])
            self.assertTrue(payload["claim_matches_remote"])
            self.assertEqual("triaged", payload["remote_state"])

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
                self.assertEqual("coordinator", kwargs["payload"]["role"])
                self.assertTrue(kwargs["payload"]["force"])
                return {"state": "claimed", "assignee": "dev-b", "lock_token": "lock-2"}

            original = gateway_ops._http_json
            gateway_ops._http_json = _http_json  # type: ignore[assignment]
            try:
                stream = io.StringIO()
                with contextlib.redirect_stdout(stream):
                    rc = gateway_ops.command_gateway_reassign(
                        argparse.Namespace(spec="demo", to_actor="dev-b", role="coordinator", force=True, ttl_seconds=120, reason="", json=True),
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
            self.assertEqual("coordinator", payload["role"])
            self.assertTrue(payload["force"])

    def test_run_with_remote_claim_heartbeat_keeps_command_protected(self) -> None:
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
            calls: list[str] = []

            def _http_json(**kwargs):  # type: ignore[no-untyped-def]
                calls.append(str(kwargs["url"]))
                return {"state": "triaged", "lock_expires_at": "2026-04-09T12:00:00+00:00"}

            original = gateway_ops._http_json
            gateway_ops._http_json = _http_json  # type: ignore[assignment]
            try:
                rc = gateway_ops.run_with_remote_claim_heartbeat(
                    root=root,
                    slug="demo",
                    read_state=lambda _slug: dict(state),
                    workspace_config=workspace_config,
                    callback=lambda: 0,
                    ttl_seconds=120,
                    interval_seconds=30,
                    reason="auto-heartbeat-test",
                )
            finally:
                gateway_ops._http_json = original  # type: ignore[assignment]

            self.assertEqual(0, rc)
            self.assertEqual(["https://gateway.example/v1/specs/demo/heartbeat"], calls)

    def test_command_gateway_pick_claims_first_eligible_spec(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_config = {"gateway": {"connection": {"mode": "remote", "base_url": "https://gateway.example"}}}
            state: dict[str, object] = {}

            def read_state(_slug: str) -> dict[str, object]:
                return dict(state)

            def write_state(_slug: str, payload: dict[str, object]) -> None:
                state.clear()
                state.update(payload)

            def _http_json(**kwargs):  # type: ignore[no-untyped-def]
                url = str(kwargs["url"])
                if url == "https://gateway.example/v1/specs":
                    return {
                        "items": [
                            {
                                "spec_id": "taken",
                                "state": "triaged",
                                "assignee": "other-dev",
                                "updated_at": "2026-04-10T00:00:00+00:00",
                                "created_at": "2026-04-09T00:00:00+00:00",
                            },
                            {
                                "spec_id": "demo",
                                "state": "triaged",
                                "assignee": None,
                                "updated_at": "2026-04-09T12:00:00+00:00",
                                "created_at": "2026-04-09T00:00:00+00:00",
                            },
                        ]
                    }
                if url == "https://gateway.example/v1/specs/demo/claim":
                    return {
                        "state": "triaged",
                        "assignee": "dev-a",
                        "lock_token": "lock-1",
                        "lock_expires_at": "2026-04-09T12:00:00+00:00",
                    }
                if url == "https://gateway.example/v1/specs/demo/source":
                    return {
                        "spec_id": "demo",
                        "path": "/workspace/specs/features/demo.spec.md",
                        "content": "---\nstatus: approved\n---\n\n# Demo\n",
                        "updated_at": "2026-04-09T00:00:00+00:00",
                        "content_sha256": "abc123",
                    }
                raise AssertionError(url)

            original = gateway_ops._http_json
            gateway_ops._http_json = _http_json  # type: ignore[assignment]
            try:
                stream = io.StringIO()
                with contextlib.redirect_stdout(stream):
                    rc = gateway_ops.command_gateway_pick(
                        argparse.Namespace(actor="dev-a", states=None, reason="", ttl_seconds=120, json=True),
                        root=root,
                        workspace_config=workspace_config,
                        read_state=read_state,
                        write_state=write_state,
                        json_dumps=self._json_dumps,
                    )
            finally:
                gateway_ops._http_json = original  # type: ignore[assignment]

            self.assertEqual(0, rc)
            payload = json.loads(stream.getvalue())
            self.assertTrue(payload["picked"])
            self.assertEqual("demo", payload["spec_id"])
            self.assertEqual("dev-a", state["gateway_claim"]["actor"])

    def test_command_gateway_poll_returns_no_eligible_specs(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_config = {"gateway": {"connection": {"mode": "remote", "base_url": "https://gateway.example"}}}
            state: dict[str, object] = {}

            def _http_json(**kwargs):  # type: ignore[no-untyped-def]
                self.assertEqual("https://gateway.example/v1/specs", kwargs["url"])
                return {"items": []}

            original = gateway_ops._http_json
            gateway_ops._http_json = _http_json  # type: ignore[assignment]
            try:
                stream = io.StringIO()
                with contextlib.redirect_stdout(stream):
                    rc = gateway_ops.command_gateway_poll(
                        argparse.Namespace(actor="dev-a", states=None, reason="", ttl_seconds=120, auto_plan=None, json=True),
                        root=root,
                        workspace_config=workspace_config,
                        read_state=lambda _slug: dict(state),
                        write_state=lambda _slug, payload: state.update(payload),
                        json_dumps=self._json_dumps,
                        auto_plan_callback=lambda _slug: 0,
                    )
            finally:
                gateway_ops._http_json = original  # type: ignore[assignment]

            self.assertEqual(0, rc)
            payload = json.loads(stream.getvalue())
            self.assertFalse(payload["picked"])
            self.assertEqual("no-eligible-specs", payload["reason"])
            self.assertFalse(payload["auto_plan_enabled"])
            self.assertEqual("default", payload["auto_plan_source"])
            self.assertFalse(payload["plan_attempted"])
            self.assertEqual("not-requested", payload["plan_status"])

    def test_command_gateway_poll_claims_first_eligible_spec(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_config = {"gateway": {"connection": {"mode": "remote", "base_url": "https://gateway.example"}}}
            state: dict[str, object] = {}

            def read_state(_slug: str) -> dict[str, object]:
                return dict(state)

            def write_state(_slug: str, payload: dict[str, object]) -> None:
                state.clear()
                state.update(payload)

            def _http_json(**kwargs):  # type: ignore[no-untyped-def]
                url = str(kwargs["url"])
                if url == "https://gateway.example/v1/specs":
                    return {
                        "items": [
                            {
                                "spec_id": "demo",
                                "state": "triaged",
                                "assignee": None,
                                "updated_at": "2026-04-09T12:00:00+00:00",
                                "created_at": "2026-04-09T00:00:00+00:00",
                            }
                        ]
                    }
                if url == "https://gateway.example/v1/specs/demo/claim":
                    return {
                        "state": "triaged",
                        "assignee": "dev-a",
                        "lock_token": "lock-1",
                        "lock_expires_at": "2026-04-09T12:00:00+00:00",
                    }
                if url == "https://gateway.example/v1/specs/demo/source":
                    return {
                        "spec_id": "demo",
                        "path": "/workspace/specs/features/demo.spec.md",
                        "content": "---\nstatus: approved\n---\n\n# Demo\n",
                        "updated_at": "2026-04-09T00:00:00+00:00",
                        "content_sha256": "abc123",
                    }
                raise AssertionError(url)

            original = gateway_ops._http_json
            gateway_ops._http_json = _http_json  # type: ignore[assignment]
            try:
                stream = io.StringIO()
                with contextlib.redirect_stdout(stream):
                    rc = gateway_ops.command_gateway_poll(
                        argparse.Namespace(actor="dev-a", states=None, reason="", ttl_seconds=120, auto_plan=None, json=True),
                        root=root,
                        workspace_config=workspace_config,
                        read_state=read_state,
                        write_state=write_state,
                        json_dumps=self._json_dumps,
                        auto_plan_callback=lambda _slug: 0,
                    )
            finally:
                gateway_ops._http_json = original  # type: ignore[assignment]

            self.assertEqual(0, rc)
            payload = json.loads(stream.getvalue())
            self.assertTrue(payload["picked"])
            self.assertEqual("demo", payload["spec_id"])
            self.assertEqual("dev-a", state["gateway_claim"]["actor"])
            self.assertFalse(payload["auto_plan_enabled"])
            self.assertEqual("default", payload["auto_plan_source"])
            self.assertFalse(payload["plan_attempted"])
            self.assertEqual("not-requested", payload["plan_status"])

    def test_command_gateway_poll_rejects_existing_local_claim(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_root = root / ".flow" / "state"
            state_root.mkdir(parents=True, exist_ok=True)
            (state_root / "claimed.json").write_text(
                json.dumps(
                    {
                        "gateway_claim": {
                            "mode": "remote",
                            "base_url": "https://gateway.example",
                            "spec_id": "claimed",
                            "actor": "dev-a",
                            "lock_token": "lock-1",
                        }
                    }
                ),
                encoding="utf-8",
            )
            workspace_config = {"gateway": {"connection": {"mode": "remote", "base_url": "https://gateway.example"}}}
            with self.assertRaises(SystemExit) as ctx:
                gateway_ops.command_gateway_poll(
                    argparse.Namespace(actor="dev-a", states=None, reason="", ttl_seconds=120, auto_plan=None, json=False),
                    root=root,
                    workspace_config=workspace_config,
                    read_state=lambda _slug: {},
                    write_state=lambda _slug, payload: None,
                    json_dumps=self._json_dumps,
                    auto_plan_callback=lambda _slug: 0,
                )
            self.assertIn("claim remoto activo", str(ctx.exception))

    def test_command_gateway_watch_stops_after_max_attempts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_config = {"gateway": {"connection": {"mode": "remote", "base_url": "https://gateway.example"}}}
            state: dict[str, object] = {}
            sleep_calls: list[float] = []
            ticks = iter([0.0, 0.0, 1.0, 2.0, 3.0])

            def _http_json(**kwargs):  # type: ignore[no-untyped-def]
                self.assertEqual("https://gateway.example/v1/specs", kwargs["url"])
                return {"items": []}

            original = gateway_ops._http_json
            gateway_ops._http_json = _http_json  # type: ignore[assignment]
            try:
                stream = io.StringIO()
                with contextlib.redirect_stdout(stream):
                    rc = gateway_ops.command_gateway_watch(
                        argparse.Namespace(
                            actor="dev-a",
                            states=None,
                            reason="",
                            ttl_seconds=120,
                            auto_plan=None,
                            interval_seconds=1.0,
                            max_interval_seconds=2.0,
                            backoff_multiplier=2.0,
                            timeout_seconds=0.0,
                            max_attempts=2,
                            json=True,
                        ),
                        root=root,
                        workspace_config=workspace_config,
                        read_state=lambda _slug: dict(state),
                        write_state=lambda _slug, payload: state.update(payload),
                        json_dumps=self._json_dumps,
                        auto_plan_callback=lambda _slug: 0,
                        sleep_fn=lambda seconds: sleep_calls.append(seconds),
                        monotonic_fn=lambda: next(ticks),
                    )
            finally:
                gateway_ops._http_json = original  # type: ignore[assignment]

            self.assertEqual(0, rc)
            payload = json.loads(stream.getvalue())
            self.assertFalse(payload["picked"])
            self.assertEqual("max-attempts-reached", payload["reason"])
            self.assertFalse(payload["auto_plan_enabled"])
            self.assertEqual("default", payload["auto_plan_source"])
            self.assertFalse(payload["plan_attempted"])
            self.assertEqual("not-requested", payload["plan_status"])
            self.assertEqual([1.0, 2.0], sleep_calls)

    def test_command_gateway_watch_stops_on_first_claim(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_config = {"gateway": {"connection": {"mode": "remote", "base_url": "https://gateway.example"}}}
            state: dict[str, object] = {}
            sleep_calls: list[float] = []
            call_count = {"list": 0}

            def read_state(_slug: str) -> dict[str, object]:
                return dict(state)

            def write_state(_slug: str, payload: dict[str, object]) -> None:
                state.clear()
                state.update(payload)

            def _http_json(**kwargs):  # type: ignore[no-untyped-def]
                url = str(kwargs["url"])
                if url == "https://gateway.example/v1/specs":
                    call_count["list"] += 1
                    if call_count["list"] == 1:
                        return {"items": []}
                    return {
                        "items": [
                            {
                                "spec_id": "demo",
                                "state": "triaged",
                                "assignee": None,
                                "updated_at": "2026-04-09T12:00:00+00:00",
                                "created_at": "2026-04-09T00:00:00+00:00",
                            }
                        ]
                    }
                if url == "https://gateway.example/v1/specs/demo/claim":
                    return {
                        "state": "triaged",
                        "assignee": "dev-a",
                        "lock_token": "lock-1",
                        "lock_expires_at": "2026-04-09T12:00:00+00:00",
                    }
                if url == "https://gateway.example/v1/specs/demo/source":
                    return {
                        "spec_id": "demo",
                        "path": "/workspace/specs/features/demo.spec.md",
                        "content": "---\nstatus: approved\n---\n\n# Demo\n",
                        "updated_at": "2026-04-09T00:00:00+00:00",
                        "content_sha256": "abc123",
                    }
                raise AssertionError(url)

            original = gateway_ops._http_json
            gateway_ops._http_json = _http_json  # type: ignore[assignment]
            try:
                stream = io.StringIO()
                with contextlib.redirect_stdout(stream):
                    rc = gateway_ops.command_gateway_watch(
                        argparse.Namespace(
                            actor="dev-a",
                            states=None,
                            reason="",
                            ttl_seconds=120,
                            auto_plan=None,
                            interval_seconds=1.0,
                            max_interval_seconds=2.0,
                            backoff_multiplier=2.0,
                            timeout_seconds=10.0,
                            max_attempts=3,
                            json=True,
                        ),
                        root=root,
                        workspace_config=workspace_config,
                        read_state=read_state,
                        write_state=write_state,
                        json_dumps=self._json_dumps,
                        auto_plan_callback=lambda _slug: 0,
                        sleep_fn=lambda seconds: sleep_calls.append(seconds),
                        monotonic_fn=lambda: 0.0,
                    )
            finally:
                gateway_ops._http_json = original  # type: ignore[assignment]

            self.assertEqual(0, rc)
            payload = json.loads(stream.getvalue())
            self.assertTrue(payload["picked"])
            self.assertEqual("demo", payload["spec_id"])
            self.assertFalse(payload["auto_plan_enabled"])
            self.assertEqual("default", payload["auto_plan_source"])
            self.assertFalse(payload["plan_attempted"])
            self.assertEqual("not-requested", payload["plan_status"])
            self.assertEqual([1.0], sleep_calls)

    def test_command_gateway_poll_uses_workspace_auto_plan_default(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_config = {
                "gateway": {
                    "connection": {"mode": "remote", "base_url": "https://gateway.example"},
                    "execution": {"auto_plan": True},
                }
            }

            def _http_json(**kwargs):  # type: ignore[no-untyped-def]
                self.assertEqual("https://gateway.example/v1/specs", kwargs["url"])
                return {"items": []}

            original = gateway_ops._http_json
            gateway_ops._http_json = _http_json  # type: ignore[assignment]
            try:
                stream = io.StringIO()
                with contextlib.redirect_stdout(stream):
                    rc = gateway_ops.command_gateway_poll(
                        argparse.Namespace(actor="dev-a", states=None, reason="", ttl_seconds=120, auto_plan=None, json=True),
                        root=root,
                        workspace_config=workspace_config,
                        read_state=lambda _slug: {},
                        write_state=lambda _slug, payload: None,
                        json_dumps=self._json_dumps,
                        auto_plan_callback=lambda _slug: 0,
                    )
            finally:
                gateway_ops._http_json = original  # type: ignore[assignment]

            self.assertEqual(0, rc)
            payload = json.loads(stream.getvalue())
            self.assertTrue(payload["auto_plan_enabled"])
            self.assertEqual("workspace", payload["auto_plan_source"])
            self.assertFalse(payload["plan_attempted"])
            self.assertEqual("not-requested", payload["plan_status"])

    def test_command_gateway_watch_cli_override_disables_workspace_auto_plan(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_config = {
                "gateway": {
                    "connection": {"mode": "remote", "base_url": "https://gateway.example"},
                    "execution": {"auto_plan": True},
                }
            }
            ticks = iter([0.0, 0.0, 1.0, 2.0, 3.0])

            def _http_json(**kwargs):  # type: ignore[no-untyped-def]
                self.assertEqual("https://gateway.example/v1/specs", kwargs["url"])
                return {"items": []}

            original = gateway_ops._http_json
            gateway_ops._http_json = _http_json  # type: ignore[assignment]
            try:
                stream = io.StringIO()
                with contextlib.redirect_stdout(stream):
                    rc = gateway_ops.command_gateway_watch(
                        argparse.Namespace(
                            actor="dev-a",
                            states=None,
                            reason="",
                            ttl_seconds=120,
                            auto_plan=False,
                            interval_seconds=1.0,
                            max_interval_seconds=2.0,
                            backoff_multiplier=2.0,
                            timeout_seconds=0.0,
                            max_attempts=1,
                            json=True,
                        ),
                        root=root,
                        workspace_config=workspace_config,
                        read_state=lambda _slug: {},
                        write_state=lambda _slug, payload: None,
                        json_dumps=self._json_dumps,
                        auto_plan_callback=lambda _slug: 0,
                        sleep_fn=lambda _seconds: None,
                        monotonic_fn=lambda: next(ticks),
                    )
            finally:
                gateway_ops._http_json = original  # type: ignore[assignment]

            self.assertEqual(0, rc)
            payload = json.loads(stream.getvalue())
            self.assertFalse(payload["auto_plan_enabled"])
            self.assertEqual("cli", payload["auto_plan_source"])
            self.assertFalse(payload["plan_attempted"])
            self.assertEqual("not-requested", payload["plan_status"])

    def test_command_gateway_poll_runs_auto_plan_once_after_claim(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_config = {"gateway": {"connection": {"mode": "remote", "base_url": "https://gateway.example"}}}
            state: dict[str, object] = {}
            callback_calls: list[str] = []

            def read_state(_slug: str) -> dict[str, object]:
                return dict(state)

            def write_state(_slug: str, payload: dict[str, object]) -> None:
                state.clear()
                state.update(payload)

            def _http_json(**kwargs):  # type: ignore[no-untyped-def]
                url = str(kwargs["url"])
                if url == "https://gateway.example/v1/specs":
                    return {
                        "items": [
                            {
                                "spec_id": "demo",
                                "state": "triaged",
                                "assignee": None,
                                "updated_at": "2026-04-09T12:00:00+00:00",
                                "created_at": "2026-04-09T00:00:00+00:00",
                            }
                        ]
                    }
                if url == "https://gateway.example/v1/specs/demo/claim":
                    return {
                        "state": "triaged",
                        "assignee": "dev-a",
                        "lock_token": "lock-1",
                        "lock_expires_at": "2026-04-09T12:00:00+00:00",
                    }
                if url == "https://gateway.example/v1/specs/demo/source":
                    return {
                        "spec_id": "demo",
                        "path": "/workspace/specs/features/demo.spec.md",
                        "content": "---\nstatus: approved\n---\n\n# Demo\n",
                        "updated_at": "2026-04-09T00:00:00+00:00",
                        "content_sha256": "abc123",
                    }
                if url == "https://gateway.example/v1/specs/demo":
                    return {
                        "spec_id": "demo",
                        "state": "triaged",
                        "assignee": "dev-a",
                        "lock_token": "lock-1",
                        "lock_expires_at": "2026-04-09T12:00:00+00:00",
                    }
                raise AssertionError(url)

            original = gateway_ops._http_json
            gateway_ops._http_json = _http_json  # type: ignore[assignment]
            try:
                stream = io.StringIO()
                with contextlib.redirect_stdout(stream):
                    rc = gateway_ops.command_gateway_poll(
                        argparse.Namespace(actor="dev-a", states=None, reason="", ttl_seconds=120, auto_plan=True, json=True),
                        root=root,
                        workspace_config=workspace_config,
                        read_state=read_state,
                        write_state=write_state,
                        json_dumps=self._json_dumps,
                        auto_plan_callback=lambda slug: callback_calls.append(slug) or 0,
                    )
            finally:
                gateway_ops._http_json = original  # type: ignore[assignment]

            self.assertEqual(0, rc)
            self.assertEqual(["demo"], callback_calls)
            payload = json.loads(stream.getvalue())
            self.assertTrue(payload["picked"])
            self.assertTrue(payload["plan_attempted"])
            self.assertEqual("passed", payload["plan_status"])
            self.assertEqual("claimed-and-planned", payload["reason"])
            self.assertTrue(payload["remote_claim_still_valid"])

    def test_command_gateway_watch_reports_auto_plan_failure_and_stops(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_config = {"gateway": {"connection": {"mode": "remote", "base_url": "https://gateway.example"}}}
            state: dict[str, object] = {}
            sleep_calls: list[float] = []

            def read_state(_slug: str) -> dict[str, object]:
                return dict(state)

            def write_state(_slug: str, payload: dict[str, object]) -> None:
                state.clear()
                state.update(payload)

            def _http_json(**kwargs):  # type: ignore[no-untyped-def]
                url = str(kwargs["url"])
                if url == "https://gateway.example/v1/specs":
                    return {
                        "items": [
                            {
                                "spec_id": "demo",
                                "state": "triaged",
                                "assignee": None,
                                "updated_at": "2026-04-09T12:00:00+00:00",
                                "created_at": "2026-04-09T00:00:00+00:00",
                            }
                        ]
                    }
                if url == "https://gateway.example/v1/specs/demo/claim":
                    return {
                        "state": "triaged",
                        "assignee": "dev-a",
                        "lock_token": "lock-1",
                        "lock_expires_at": "2026-04-09T12:00:00+00:00",
                    }
                if url == "https://gateway.example/v1/specs/demo/source":
                    return {
                        "spec_id": "demo",
                        "path": "/workspace/specs/features/demo.spec.md",
                        "content": "---\nstatus: approved\n---\n\n# Demo\n",
                        "updated_at": "2026-04-09T00:00:00+00:00",
                        "content_sha256": "abc123",
                    }
                if url == "https://gateway.example/v1/specs/demo":
                    return {
                        "spec_id": "demo",
                        "state": "triaged",
                        "assignee": "dev-a",
                        "lock_token": "lock-1",
                        "lock_expires_at": "2026-04-09T12:00:00+00:00",
                    }
                raise AssertionError(url)

            original = gateway_ops._http_json
            gateway_ops._http_json = _http_json  # type: ignore[assignment]
            try:
                stream = io.StringIO()
                with contextlib.redirect_stdout(stream):
                    rc = gateway_ops.command_gateway_watch(
                        argparse.Namespace(
                            actor="dev-a",
                            states=None,
                            reason="",
                            ttl_seconds=120,
                            auto_plan=True,
                            interval_seconds=1.0,
                            max_interval_seconds=2.0,
                            backoff_multiplier=2.0,
                            timeout_seconds=10.0,
                            max_attempts=3,
                            json=True,
                        ),
                        root=root,
                        workspace_config=workspace_config,
                        read_state=read_state,
                        write_state=write_state,
                        json_dumps=self._json_dumps,
                        auto_plan_callback=lambda _slug: (_ for _ in ()).throw(SystemExit("boom-plan")),
                        sleep_fn=lambda seconds: sleep_calls.append(seconds),
                        monotonic_fn=lambda: 0.0,
                    )
            finally:
                gateway_ops._http_json = original  # type: ignore[assignment]

            self.assertEqual(1, rc)
            self.assertEqual([], sleep_calls)
            payload = json.loads(stream.getvalue())
            self.assertTrue(payload["picked"])
            self.assertTrue(payload["plan_attempted"])
            self.assertEqual("failed", payload["plan_status"])
            self.assertEqual("plan-failed-after-claim", payload["reason"])
            self.assertEqual("boom-plan", payload["auto_plan_error"])
            self.assertTrue(payload["remote_claim_still_valid"])

    def test_command_gateway_poll_reports_claim_not_valid_for_plan(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_config = {"gateway": {"connection": {"mode": "remote", "base_url": "https://gateway.example"}}}
            state: dict[str, object] = {}

            def read_state(_slug: str) -> dict[str, object]:
                return dict(state)

            def write_state(_slug: str, payload: dict[str, object]) -> None:
                state.clear()
                state.update(payload)

            def _http_json(**kwargs):  # type: ignore[no-untyped-def]
                url = str(kwargs["url"])
                if url == "https://gateway.example/v1/specs":
                    return {
                        "items": [
                            {
                                "spec_id": "demo",
                                "state": "triaged",
                                "assignee": None,
                                "updated_at": "2026-04-09T12:00:00+00:00",
                                "created_at": "2026-04-09T00:00:00+00:00",
                            }
                        ]
                    }
                if url == "https://gateway.example/v1/specs/demo/claim":
                    return {
                        "state": "triaged",
                        "assignee": "dev-a",
                        "lock_token": "lock-1",
                        "lock_expires_at": "2026-04-09T12:00:00+00:00",
                    }
                if url == "https://gateway.example/v1/specs/demo/source":
                    return {
                        "spec_id": "demo",
                        "path": "/workspace/specs/features/demo.spec.md",
                        "content": "---\nstatus: approved\n---\n\n# Demo\n",
                        "updated_at": "2026-04-09T00:00:00+00:00",
                        "content_sha256": "abc123",
                    }
                if url == "https://gateway.example/v1/specs/demo":
                    return {
                        "spec_id": "demo",
                        "state": "triaged",
                        "assignee": "other-dev",
                        "lock_token": "lock-2",
                        "lock_expires_at": "2026-04-09T12:00:00+00:00",
                    }
                raise AssertionError(url)

            original = gateway_ops._http_json
            gateway_ops._http_json = _http_json  # type: ignore[assignment]
            try:
                stream = io.StringIO()
                with contextlib.redirect_stdout(stream):
                    rc = gateway_ops.command_gateway_poll(
                        argparse.Namespace(actor="dev-a", states=None, reason="", ttl_seconds=120, auto_plan=True, json=True),
                        root=root,
                        workspace_config=workspace_config,
                        read_state=read_state,
                        write_state=write_state,
                        json_dumps=self._json_dumps,
                        auto_plan_callback=lambda _slug: (_ for _ in ()).throw(
                            SystemExit("La spec `demo` ya no tiene claim remoto vigente para `dev-a`.")
                        ),
                    )
            finally:
                gateway_ops._http_json = original  # type: ignore[assignment]

            self.assertEqual(1, rc)
            payload = json.loads(stream.getvalue())
            self.assertTrue(payload["picked"])
            self.assertTrue(payload["plan_attempted"])
            self.assertEqual("failed", payload["plan_status"])
            self.assertEqual("claim-not-valid-for-plan", payload["reason"])
            self.assertFalse(payload["remote_claim_still_valid"])

    def test_command_gateway_watch_auto_plan_success_stops_without_extra_sleep(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_config = {"gateway": {"connection": {"mode": "remote", "base_url": "https://gateway.example"}}}
            state: dict[str, object] = {}
            sleep_calls: list[float] = []
            callback_calls: list[str] = []

            def read_state(_slug: str) -> dict[str, object]:
                return dict(state)

            def write_state(_slug: str, payload: dict[str, object]) -> None:
                state.clear()
                state.update(payload)

            def _http_json(**kwargs):  # type: ignore[no-untyped-def]
                url = str(kwargs["url"])
                if url == "https://gateway.example/v1/specs":
                    return {
                        "items": [
                            {
                                "spec_id": "demo",
                                "state": "triaged",
                                "assignee": None,
                                "updated_at": "2026-04-09T12:00:00+00:00",
                                "created_at": "2026-04-09T00:00:00+00:00",
                            }
                        ]
                    }
                if url == "https://gateway.example/v1/specs/demo/claim":
                    return {
                        "state": "triaged",
                        "assignee": "dev-a",
                        "lock_token": "lock-1",
                        "lock_expires_at": "2026-04-09T12:00:00+00:00",
                    }
                if url == "https://gateway.example/v1/specs/demo/source":
                    return {
                        "spec_id": "demo",
                        "path": "/workspace/specs/features/demo.spec.md",
                        "content": "---\nstatus: approved\n---\n\n# Demo\n",
                        "updated_at": "2026-04-09T00:00:00+00:00",
                        "content_sha256": "abc123",
                    }
                if url == "https://gateway.example/v1/specs/demo":
                    return {
                        "spec_id": "demo",
                        "state": "triaged",
                        "assignee": "dev-a",
                        "lock_token": "lock-1",
                        "lock_expires_at": "2026-04-09T12:00:00+00:00",
                    }
                raise AssertionError(url)

            original = gateway_ops._http_json
            gateway_ops._http_json = _http_json  # type: ignore[assignment]
            try:
                stream = io.StringIO()
                with contextlib.redirect_stdout(stream):
                    rc = gateway_ops.command_gateway_watch(
                        argparse.Namespace(
                            actor="dev-a",
                            states=None,
                            reason="",
                            ttl_seconds=120,
                            auto_plan=True,
                            interval_seconds=1.0,
                            max_interval_seconds=2.0,
                            backoff_multiplier=2.0,
                            timeout_seconds=10.0,
                            max_attempts=3,
                            json=True,
                        ),
                        root=root,
                        workspace_config=workspace_config,
                        read_state=read_state,
                        write_state=write_state,
                        json_dumps=self._json_dumps,
                        auto_plan_callback=lambda slug: callback_calls.append(slug) or 0,
                        sleep_fn=lambda seconds: sleep_calls.append(seconds),
                        monotonic_fn=lambda: 0.0,
                    )
            finally:
                gateway_ops._http_json = original  # type: ignore[assignment]

            self.assertEqual(0, rc)
            self.assertEqual(["demo"], callback_calls)
            self.assertEqual([], sleep_calls)
            payload = json.loads(stream.getvalue())
            self.assertTrue(payload["picked"])
            self.assertTrue(payload["plan_attempted"])
            self.assertEqual("passed", payload["plan_status"])

    def test_command_gateway_poll_auto_plan_smoke_materializes_plan_and_transitions(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "api" / "app").mkdir(parents=True, exist_ok=True)
            workspace_config = {"gateway": {"connection": {"mode": "remote", "base_url": "https://gateway.example"}}}
            spec_body = """---
schema_version: 3
name: demo
description: demo
status: approved
owner: platform
single_slice_reason: "smoke single-slice fixture"
multi_domain: false
phases: []
depends_on: []
required_runtimes: []
required_services: []
required_capabilities: []
stack_projects: []
stack_services: []
stack_capabilities: []
targets:
  - ../../api/app/**
---

# demo

## Slice Breakdown

```yaml
- name: api-main
  targets:
    - ../../api/app/**
  hot_area: api/app
  depends_on: []
```
"""
            state: dict[str, object] = {}
            calls: list[str] = []
            remote_state = {"state": "new"}
            config = self._spec_config(root)
            plan_root = root / ".flow" / "plans"
            worktree_root = root / ".worktrees"

            def read_state(_slug: str) -> dict[str, object]:
                return dict(state)

            def write_state(_slug: str, payload: dict[str, object]) -> None:
                state.clear()
                state.update(payload)

            def _http_json(**kwargs):  # type: ignore[no-untyped-def]
                url = str(kwargs["url"])
                calls.append(f"{kwargs['method']} {url}")
                if url == "https://gateway.example/v1/specs":
                    return {
                        "items": [
                            {
                                "spec_id": "demo",
                                "state": remote_state["state"],
                                "assignee": None,
                                "updated_at": "2026-04-09T12:00:00+00:00",
                                "created_at": "2026-04-09T00:00:00+00:00",
                            }
                        ]
                    }
                if url == "https://gateway.example/v1/specs/demo/claim":
                    return {
                        "state": remote_state["state"],
                        "assignee": "dev-a",
                        "lock_token": "lock-1",
                        "lock_expires_at": "2026-04-09T12:00:00+00:00",
                    }
                if url == "https://gateway.example/v1/specs/demo/source":
                    return {
                        "spec_id": "demo",
                        "path": "/workspace/specs/features/demo.spec.md",
                        "content": spec_body,
                        "updated_at": "2026-04-09T00:00:00+00:00",
                        "content_sha256": "abc123",
                    }
                if url == "https://gateway.example/v1/specs/demo":
                    return {
                        "spec_id": "demo",
                        "state": remote_state["state"],
                        "assignee": "dev-a",
                        "lock_token": "lock-1",
                        "lock_expires_at": "2026-04-09T12:00:00+00:00",
                    }
                if url == "https://gateway.example/v1/specs/demo/heartbeat":
                    return {
                        "state": remote_state["state"],
                        "lock_expires_at": "2026-04-09T12:00:00+00:00",
                    }
                if url == "https://gateway.example/v1/specs/demo/transition":
                    remote_state["state"] = "triaged"
                    return {"spec_id": "demo", "state": "triaged"}
                raise AssertionError(url)

            def _auto_plan_callback(slug: str) -> int:
                def _callback() -> int:
                    return command_plan(
                        argparse.Namespace(spec=slug),
                        require_dirs=lambda: plan_root.mkdir(parents=True, exist_ok=True),
                        resolve_spec=lambda _spec: root / "specs" / "features" / f"{slug}.spec.md",
                        spec_slug=lambda _path: slug,
                        analyze_spec=lambda path: analyze_spec(path, config=config),
                        require_routed_paths=lambda paths, label: require_routed_paths(paths, label, config=config),
                        repo_slice_prefix=lambda repo: repo,
                        repo_root=lambda repo: root / repo,
                        worktree_root=worktree_root,
                        plan_root=plan_root,
                        read_state=read_state,
                        write_state=write_state,
                        ensure_remote_claim_for_plan=lambda claim_slug: gateway_ops.ensure_remote_claim_for_plan(
                            root=root,
                            slug=claim_slug,
                            read_state=read_state,
                            workspace_config=workspace_config,
                        ),
                        rel=lambda path: str(path),
                        utc_now=lambda: "2026-04-10T00:00:00+00:00",
                    )

                rc = gateway_ops.run_with_remote_claim_heartbeat(
                    root=root,
                    slug=slug,
                    read_state=read_state,
                    workspace_config=workspace_config,
                    callback=_callback,
                    reason="auto-heartbeat-plan",
                )
                if rc == 0:
                    gateway_ops.maybe_publish_transition_hook(
                        root=root,
                        slug=slug,
                        read_state=read_state,
                        workspace_config=workspace_config,
                        to_state="triaged",
                        reason="hook-plan-succeeded",
                    )
                return rc

            original = gateway_ops._http_json
            gateway_ops._http_json = _http_json  # type: ignore[assignment]
            try:
                stream = io.StringIO()
                with contextlib.redirect_stdout(stream):
                    rc = gateway_ops.command_gateway_poll(
                        argparse.Namespace(actor="dev-a", states=None, reason="", ttl_seconds=120, auto_plan=True, json=True),
                        root=root,
                        workspace_config=workspace_config,
                        read_state=read_state,
                        write_state=write_state,
                        json_dumps=self._json_dumps,
                        auto_plan_callback=_auto_plan_callback,
                    )
            finally:
                gateway_ops._http_json = original  # type: ignore[assignment]

            self.assertEqual(0, rc)
            self.assertTrue((plan_root / "demo.json").is_file())
            lines = stream.getvalue().splitlines()
            json_start = max(idx for idx, line in enumerate(lines) if line.strip() == "{")
            payload = json.loads("\n".join(lines[json_start:]))
            self.assertTrue(payload["picked"])
            self.assertTrue(payload["plan_attempted"])
            self.assertEqual("passed", payload["plan_status"])
            self.assertEqual("claimed-and-planned", payload["reason"])
            self.assertTrue(payload["remote_claim_still_valid"])
            self.assertIn("POST https://gateway.example/v1/specs/demo/heartbeat", calls)
            self.assertIn("POST https://gateway.example/v1/specs/demo/transition", calls)

    def test_maybe_publish_transition_hook_skips_redundant_remote_state(self) -> None:
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
            calls: list[str] = []

            def _http_json(**kwargs):  # type: ignore[no-untyped-def]
                calls.append(f"{kwargs['method']} {kwargs['url']}")
                if kwargs["url"] == "https://gateway.example/v1/specs/demo":
                    return {
                        "spec_id": "demo",
                        "state": "triaged",
                        "assignee": "dev-a",
                        "lock_token": "lock-1",
                        "lock_expires_at": "2026-04-09T12:00:00+00:00",
                    }
                raise AssertionError(kwargs["url"])

            original = gateway_ops._http_json
            gateway_ops._http_json = _http_json  # type: ignore[assignment]
            try:
                gateway_ops.maybe_publish_transition_hook(
                    root=root,
                    slug="demo",
                    read_state=lambda _slug: dict(state),
                    workspace_config=workspace_config,
                    to_state="triaged",
                    reason="hook-plan-succeeded",
                )
            finally:
                gateway_ops._http_json = original  # type: ignore[assignment]

            self.assertEqual(["GET https://gateway.example/v1/specs/demo"], calls)

    def test_maybe_publish_transition_hook_publishes_when_state_changes(self) -> None:
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
            calls: list[str] = []

            def _http_json(**kwargs):  # type: ignore[no-untyped-def]
                calls.append(f"{kwargs['method']} {kwargs['url']}")
                if kwargs["url"] == "https://gateway.example/v1/specs/demo":
                    return {
                        "spec_id": "demo",
                        "state": "new",
                        "assignee": "dev-a",
                        "lock_token": "lock-1",
                        "lock_expires_at": "2026-04-09T12:00:00+00:00",
                    }
                if kwargs["url"] == "https://gateway.example/v1/specs/demo/transition":
                    return {"spec_id": "demo", "state": "triaged"}
                raise AssertionError(kwargs["url"])

            original = gateway_ops._http_json
            gateway_ops._http_json = _http_json  # type: ignore[assignment]
            try:
                gateway_ops.maybe_publish_transition_hook(
                    root=root,
                    slug="demo",
                    read_state=lambda _slug: dict(state),
                    workspace_config=workspace_config,
                    to_state="triaged",
                    reason="hook-plan-succeeded",
                )
            finally:
                gateway_ops._http_json = original  # type: ignore[assignment]

            self.assertEqual(
                [
                    "GET https://gateway.example/v1/specs/demo",
                    "POST https://gateway.example/v1/specs/demo/transition",
                ],
                calls,
            )

    def test_maybe_publish_transition_hook_skips_non_sequential_transition(self) -> None:
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
            calls: list[str] = []

            def _http_json(**kwargs):  # type: ignore[no-untyped-def]
                calls.append(f"{kwargs['method']} {kwargs['url']}")
                if kwargs["url"] == "https://gateway.example/v1/specs/demo":
                    return {
                        "spec_id": "demo",
                        "state": "in_edit",
                        "assignee": "dev-a",
                        "lock_token": "lock-1",
                        "lock_expires_at": "2026-04-09T12:00:00+00:00",
                    }
                raise AssertionError(kwargs["url"])

            original = gateway_ops._http_json
            gateway_ops._http_json = _http_json  # type: ignore[assignment]
            try:
                gateway_ops.maybe_publish_transition_hook(
                    root=root,
                    slug="demo",
                    read_state=lambda _slug: dict(state),
                    workspace_config=workspace_config,
                    to_state="triaged",
                    reason="hook-plan-succeeded",
                )
            finally:
                gateway_ops._http_json = original  # type: ignore[assignment]

            self.assertEqual(["GET https://gateway.example/v1/specs/demo"], calls)


if __name__ == "__main__":
    unittest.main()
