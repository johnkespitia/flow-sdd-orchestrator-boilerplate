from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from flowctl.features import file_sha256
from flowctl.policy import command_policy_check, policy_check_payload


def _json_dumps(payload: object) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True)


class PolicyCheckTests(unittest.TestCase):
    def test_plan_stage_requires_spec_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec_path = root / "sample.spec.md"
            spec_path.write_text("---\nname: Sample\nstatus: approved\n---\n# Sample\n", encoding="utf-8")

            payload = policy_check_payload(
                stage="plan",
                slug="sample",
                spec_path=spec_path,
                plan_path=root / ".flow" / "plans" / "sample.json",
                state={},
                rel=lambda path: str(path.relative_to(root)),
            )

            self.assertFalse(payload["allowed"])
            self.assertIn("spec_approval:missing_approval", payload["blocked_reasons"])

    def test_slice_start_stage_requires_current_plan_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec_path = root / "sample.spec.md"
            plan_path = root / ".flow" / "plans" / "sample.json"
            plan_path.parent.mkdir(parents=True)
            spec_path.write_text("---\nname: Sample\nstatus: approved\n---\n# Sample\n", encoding="utf-8")
            plan_path.write_text('{"feature":"sample","slices":[]}\n', encoding="utf-8")
            state = {
                "last_approval": {
                    "spec_hash": file_sha256(spec_path),
                    "spec_mtime_ns": spec_path.stat().st_mtime_ns,
                },
                "plan_approval": {
                    "status": "approved",
                    "spec_hash": file_sha256(spec_path),
                    "plan_hash": file_sha256(plan_path),
                    "plan_json": str(plan_path.relative_to(root)),
                },
            }

            payload = policy_check_payload(
                stage="slice-start",
                slug="sample",
                spec_path=spec_path,
                plan_path=plan_path,
                state=state,
                rel=lambda path: str(path.relative_to(root)),
            )

            self.assertTrue(payload["allowed"])
            self.assertEqual([], payload["blocked_reasons"])

    def test_command_policy_check_returns_blocking_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec_path = root / "sample.spec.md"
            plan_root = root / ".flow" / "plans"
            plan_root.mkdir(parents=True)
            spec_path.write_text("---\nname: Sample\nstatus: approved\n---\n# Sample\n", encoding="utf-8")
            captured: dict[str, object] = {}

            def capture(payload: object) -> str:
                self.assertIsInstance(payload, dict)
                captured.update(payload)
                return _json_dumps(payload)

            rc = command_policy_check(
                Namespace(spec="sample", stage="slice-start", json=True),
                resolve_spec=lambda _spec: spec_path,
                spec_slug=lambda _path: "sample",
                plan_root=plan_root,
                read_state=lambda _slug: {},
                rel=lambda path: str(path.relative_to(root)),
                json_dumps=capture,
            )

            self.assertEqual(2, rc)
            self.assertFalse(captured["allowed"])
            self.assertIn("spec_approval:missing_approval", captured["blocked_reasons"])
            self.assertIn("plan_approval:missing_plan", captured["blocked_reasons"])


if __name__ == "__main__":
    unittest.main()
