from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from flowctl.features import command_spec_approval_status, command_spec_approve, file_sha256


def _json_dumps(payload: object) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True)


class SpecApprovalGateTests(unittest.TestCase):
    def test_spec_approve_records_hash_of_approved_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec_path = root / "sample.spec.md"
            spec_path.write_text(
                "---\nname: Sample\nstatus: draft\n---\n# Sample\n",
                encoding="utf-8",
            )
            state: dict[str, object] = {
                "last_review": {
                    "report": ".flow/reports/sample-spec-review.md",
                    "ready_to_approve": True,
                    "spec_hash": file_sha256(spec_path),
                    "spec_mtime_ns": spec_path.stat().st_mtime_ns,
                }
            }

            def replace_status(path: Path, status: str) -> None:
                path.write_text(path.read_text(encoding="utf-8").replace("status: draft", f"status: {status}"), encoding="utf-8")

            rc = command_spec_approve(
                Namespace(spec="sample", approver="john"),
                resolve_spec=lambda _spec: spec_path,
                spec_slug=lambda _path: "sample",
                ensure_spec_ready_for_approval=lambda _path: {"frontmatter": {"name": "Sample"}, "target_index": {}},
                replace_frontmatter_status=replace_status,
                read_state=lambda _slug: state,
                write_state=lambda _slug, payload: state.update(payload),
                rel=lambda path: str(path.relative_to(root)),
                utc_now=lambda: "2026-04-16T00:00:00Z",
            )

            self.assertEqual(0, rc)
            approval = state["last_approval"]
            self.assertIsInstance(approval, dict)
            self.assertEqual("approved", approval["frontmatter_status"])
            self.assertEqual(file_sha256(spec_path), approval["spec_hash"])
            self.assertNotEqual(approval["review_spec_hash"], approval["spec_hash"])

    def test_approval_status_invalidates_when_spec_content_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec_path = root / "sample.spec.md"
            spec_path.write_text("---\nname: Sample\nstatus: approved\n---\n# Sample\n", encoding="utf-8")
            state = {
                "last_approval": {
                    "approver": "john",
                    "approved_at": "2026-04-16T00:00:00Z",
                    "spec_hash": file_sha256(spec_path),
                    "spec_mtime_ns": spec_path.stat().st_mtime_ns,
                }
            }

            rc = command_spec_approval_status(
                Namespace(spec="sample", json=True),
                resolve_spec=lambda _spec: spec_path,
                spec_slug=lambda _path: "sample",
                read_state=lambda _slug: state,
                rel=lambda path: str(path.relative_to(root)),
                json_dumps=_json_dumps,
            )
            self.assertEqual(0, rc)

            spec_path.write_text(spec_path.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")
            captured: dict[str, object] = {}

            def capture(payload: object) -> str:
                self.assertIsInstance(payload, dict)
                captured.update(payload)
                return _json_dumps(payload)

            rc = command_spec_approval_status(
                Namespace(spec="sample", json=True),
                resolve_spec=lambda _spec: spec_path,
                spec_slug=lambda _path: "sample",
                read_state=lambda _slug: state,
                rel=lambda path: str(path.relative_to(root)),
                json_dumps=capture,
            )

            self.assertEqual(0, rc)
            self.assertFalse(captured["approved"])
            self.assertIn("spec_hash_changed", captured["invalid_reasons"])


if __name__ == "__main__":
    unittest.main()
