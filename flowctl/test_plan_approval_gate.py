from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from flowctl.features import command_plan_approval_status, command_plan_approve, file_sha256


def _json_dumps(payload: object) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True)


class PlanApprovalGateTests(unittest.TestCase):
    def test_plan_approve_requires_current_spec_approval_and_records_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec_path = root / "sample.spec.md"
            plan_root = root / ".flow" / "plans"
            plan_root.mkdir(parents=True)
            plan_path = plan_root / "sample.json"
            spec_path.write_text("---\nname: Sample\nstatus: approved\n---\n# Sample\n", encoding="utf-8")
            plan_path.write_text('{"feature":"sample","slices":[]}\n', encoding="utf-8")
            state: dict[str, object] = {
                "last_approval": {
                    "spec_hash": file_sha256(spec_path),
                    "spec_mtime_ns": spec_path.stat().st_mtime_ns,
                }
            }

            rc = command_plan_approve(
                Namespace(spec="sample", approver="john"),
                resolve_spec=lambda _spec: spec_path,
                spec_slug=lambda _path: "sample",
                plan_root=plan_root,
                read_state=lambda _slug: state,
                write_state=lambda _slug, payload: state.update(payload),
                rel=lambda path: str(path.relative_to(root)),
                utc_now=lambda: "2026-04-16T00:00:00Z",
            )

            self.assertEqual(0, rc)
            approval = state["plan_approval"]
            self.assertIsInstance(approval, dict)
            self.assertEqual(file_sha256(spec_path), approval["spec_hash"])
            self.assertEqual(file_sha256(plan_path), approval["plan_hash"])

    def test_plan_approval_status_invalidates_when_plan_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec_path = root / "sample.spec.md"
            plan_root = root / ".flow" / "plans"
            plan_root.mkdir(parents=True)
            plan_path = plan_root / "sample.json"
            spec_path.write_text("---\nname: Sample\nstatus: approved\n---\n# Sample\n", encoding="utf-8")
            plan_path.write_text('{"feature":"sample","slices":[]}\n', encoding="utf-8")
            state = {
                "plan_approval": {
                    "status": "approved",
                    "spec_hash": file_sha256(spec_path),
                    "plan_hash": file_sha256(plan_path),
                }
            }
            plan_path.write_text('{"feature":"sample","slices":[{"name":"changed"}]}\n', encoding="utf-8")
            captured: dict[str, object] = {}

            def capture(payload: object) -> str:
                self.assertIsInstance(payload, dict)
                captured.update(payload)
                return _json_dumps(payload)

            rc = command_plan_approval_status(
                Namespace(spec="sample", json=True),
                resolve_spec=lambda _spec: spec_path,
                spec_slug=lambda _path: "sample",
                plan_root=plan_root,
                read_state=lambda _slug: state,
                rel=lambda path: str(path.relative_to(root)),
                json_dumps=capture,
            )

            self.assertEqual(0, rc)
            self.assertFalse(captured["approved"])
            self.assertIn("plan_hash_changed", captured["invalid_reasons"])


if __name__ == "__main__":
    unittest.main()
