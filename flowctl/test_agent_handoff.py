from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from flowctl.agent_handoff import agent_handoff_payload, write_agent_handoff
from flowctl.features import file_sha256


class AgentHandoffTests(unittest.TestCase):
    def test_agent_handoff_writes_package_and_copies_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec_path = root / "specs" / "features" / "sample.spec.md"
            plan_path = root / ".flow" / "plans" / "sample.json"
            report_root = root / ".flow" / "reports"
            evidence_root = report_root / "evidence"
            handoff_root = report_root / "agent-handoffs"
            spec_path.parent.mkdir(parents=True)
            plan_path.parent.mkdir(parents=True)
            (report_root / "ci").mkdir(parents=True)
            spec_path.write_text("---\nname: Sample\nstatus: approved\n---\n# Sample\n", encoding="utf-8")
            plan_path.write_text(
                json.dumps(
                    {
                        "feature": "sample",
                        "slices": [
                            {
                                "name": "core",
                                "repo": "root",
                                "branch": "feat/sample-core",
                                "worktree": ".worktrees/root-sample-core",
                                "owned_targets": ["../../flow"],
                                "acceptable_evidence": ["python3 -m unittest flowctl.test_agent_handoff"],
                                "executor_mode": "compliance-closeout",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (report_root / "ci" / "spec-sample.json").write_text(
                json.dumps({"items": [{"spec": str(spec_path), "status": "passed"}]}),
                encoding="utf-8",
            )
            state = {
                "last_approval": {
                    "spec_hash": file_sha256(spec_path),
                    "spec_mtime_ns": spec_path.stat().st_mtime_ns,
                },
                "plan_approval": {
                    "status": "approved",
                    "spec_hash": file_sha256(spec_path),
                    "plan_hash": file_sha256(plan_path),
                    "plan_json": ".flow/plans/sample.json",
                },
            }

            payload = agent_handoff_payload(
                slug="sample",
                spec_path=spec_path,
                plan_path=plan_path,
                state=state,
                report_root=report_root,
                evidence_report_root=evidence_root,
                handoff_report_root=handoff_root,
                root=root,
                rel=lambda path: str(path.relative_to(root)),
                utc_now=lambda: "2026-04-17T00:00:00Z",
            )
            output = write_agent_handoff(payload=payload, handoff_report_root=handoff_root, rel=lambda path: str(path.relative_to(root)))

            self.assertTrue(output["ready_for_agent"])
            self.assertEqual([], output["blocked_actions"])
            self.assertEqual("core", output["slices"][0]["name"])
            self.assertTrue((root / str(output["json_report"])).is_file())
            self.assertTrue((root / str(output["markdown_report"])).is_file())
            self.assertTrue((handoff_root / "sample" / spec_path.name).is_file())
            self.assertTrue((handoff_root / "sample" / plan_path.name).is_file())

    def test_agent_handoff_reports_blockers_when_evidence_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec_path = root / "specs" / "features" / "sample.spec.md"
            plan_path = root / ".flow" / "plans" / "sample.json"
            spec_path.parent.mkdir(parents=True)
            plan_path.parent.mkdir(parents=True)
            spec_path.write_text("---\nname: Sample\nstatus: draft\n---\n# Sample\n", encoding="utf-8")
            plan_path.write_text('{"feature":"sample","slices":[]}\n', encoding="utf-8")

            payload = agent_handoff_payload(
                slug="sample",
                spec_path=spec_path,
                plan_path=plan_path,
                state={},
                report_root=root / ".flow" / "reports",
                evidence_report_root=root / ".flow" / "reports" / "evidence",
                handoff_report_root=root / ".flow" / "reports" / "agent-handoffs",
                root=root,
                rel=lambda path: str(path.relative_to(root)),
                utc_now=lambda: "2026-04-17T00:00:00Z",
            )

            self.assertFalse(payload["ready_for_agent"])
            self.assertIn("spec_approval", payload["blocked_actions"])
            self.assertIn("plan_approval", payload["blocked_actions"])
            self.assertTrue(payload["next_commands"][0].startswith("python3 ./flow spec approve"))
            self.assertTrue(payload["next_commands"][1].startswith("python3 ./flow plan-approve"))


if __name__ == "__main__":
    unittest.main()
