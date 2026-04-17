from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from flowctl.evidence import evidence_status_payload, write_evidence_bundle
from flowctl.features import file_sha256


class EvidenceTests(unittest.TestCase):
    def test_evidence_status_reports_missing_plan_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec_path = root / "specs" / "features" / "sample.spec.md"
            plan_path = root / ".flow" / "plans" / "sample.json"
            report_root = root / ".flow" / "reports"
            spec_path.parent.mkdir(parents=True)
            plan_path.parent.mkdir(parents=True)
            (report_root / "ci").mkdir(parents=True)
            (report_root / "agent-handoffs").mkdir(parents=True)
            spec_path.write_text("---\nname: Sample\nstatus: approved\n---\n# Sample\n", encoding="utf-8")
            plan_path.write_text('{"feature":"sample","slices":[]}\n', encoding="utf-8")
            (report_root / "ci" / "spec-sample.json").write_text(
                json.dumps({"items": [{"spec": str(spec_path), "status": "passed"}]}),
                encoding="utf-8",
            )
            (report_root / "agent-handoffs" / "sample-agent-handoff.json").write_text(
                json.dumps({"feature": "sample"}),
                encoding="utf-8",
            )
            state = {
                "last_approval": {
                    "spec_hash": file_sha256(spec_path),
                    "spec_mtime_ns": spec_path.stat().st_mtime_ns,
                }
            }

            payload = evidence_status_payload(
                slug="sample",
                spec_path=spec_path,
                plan_path=plan_path,
                state=state,
                report_root=report_root,
                rel=lambda path: str(path.relative_to(root)),
                utc_now=lambda: "2026-04-16T00:00:00Z",
            )

            self.assertFalse(payload["ready_for_release"])
            self.assertIn("plan_approval", payload["missing"])
            self.assertTrue(payload["ci_spec"]["passed"])
            self.assertEqual(1, len(payload["reports"]))

    def test_write_evidence_bundle_copies_matching_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_root = root / ".flow" / "reports"
            evidence_root = report_root / "evidence"
            source = report_root / "ci" / "spec-sample.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"status":"passed"}\n', encoding="utf-8")
            payload = {
                "feature": "sample",
                "ready_for_release": False,
                "missing": ["plan_approval"],
                "spec_path": "specs/features/sample.spec.md",
                "plan_path": ".flow/plans/sample.json",
                "reports": [{"path": ".flow/reports/ci/spec-sample.json", "kind": "ci", "format": "json"}],
            }

            bundle = write_evidence_bundle(
                payload=payload,
                evidence_report_root=evidence_root,
                root=root,
                rel=lambda path: str(path.relative_to(root)),
            )

            bundle_info = bundle["bundle"]
            self.assertIsInstance(bundle_info, dict)
            self.assertTrue((root / str(bundle_info["json_report"])).is_file())
            self.assertTrue((root / str(bundle_info["markdown_report"])).is_file())
            copied = root / ".flow" / "reports" / "evidence" / "sample" / "spec-sample.json"
            self.assertTrue(copied.is_file())


if __name__ == "__main__":
    unittest.main()
