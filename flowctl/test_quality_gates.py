from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from flowctl import quality_gates, workflows


class QualityGatesTests(unittest.TestCase):
    def test_required_checkpoint_names_match_stage_canonical(self) -> None:
        self.assertIn("slice_start-stage-pass", quality_gates.required_checkpoints("slice_start", "low", False))
        self.assertIn("ci_spec-stage-pass", quality_gates.required_checkpoints("ci_spec", "low", False))
        self.assertIn("ci_repo-stage-pass", quality_gates.required_checkpoints("ci_repo", "low", False))
        self.assertIn("ci_integration-stage-pass", quality_gates.required_checkpoints("ci_integration", "low", False))

    def test_risk_levels_all_tiers(self) -> None:
        low = quality_gates.classify_slice_risk({"owned_targets": ["frontend/ui/button.tsx"]})
        medium = quality_gates.classify_slice_risk({"owned_targets": [f"repo/file-{idx}.py" for idx in range(6)]})
        high = quality_gates.classify_slice_risk({"owned_targets": ["backend/api/orders.py"]})
        critical = quality_gates.classify_slice_risk({"owned_targets": ["backend/db/migrations/001_init.sql"]})
        self.assertEqual("low", low["level"])
        self.assertEqual("medium", medium["level"])
        self.assertEqual("high", high["level"])
        self.assertEqual("critical", critical["level"])

    def test_matrix_and_slice_score_generated(self) -> None:
        plan = {"slices": [{"name": "api", "owned_targets": ["backend/api/users.py"], "linked_tests": ["backend/tests/test_users.py"]}]}
        stage_records = {"ci_spec": {"status": "passed"}, "ci_repo": {"status": "passed"}, "ci_integration": {"status": "passed"}}
        score = quality_gates.slice_confidence_score(
            slice_payload=plan["slices"][0],
            stage_records=stage_records,
            contract_ok=True,
            drift_ok=True,
        )
        matrix = quality_gates.build_traceability_matrix(
            feature_slug="softos-quality-gates-traceability-and-risk",
            plan_payload=plan,
            state={"slice_results": {"api": {"commit_ref": "abc123"}}},
            stage_records={"release_promote": {"status": "passed"}, "release_verify": {"status": "passed"}},
        )
        self.assertGreaterEqual(int(score["score"]), 80)
        self.assertEqual(1, len(matrix))
        self.assertEqual("abc123", matrix[0]["commit"])

    def test_slice_score_treats_skipped_ci_as_idempotent_healthy(self) -> None:
        plan = {"slices": [{"name": "api", "owned_targets": ["backend/api/users.py"], "linked_tests": ["backend/tests/test_users.py"]}]}
        score = quality_gates.slice_confidence_score(
            slice_payload=plan["slices"][0],
            stage_records={"ci_spec": {"status": "skipped"}, "ci_repo": {"status": "skipped"}, "ci_integration": {"status": "skipped"}},
            contract_ok=True,
            drift_ok=True,
        )
        self.assertGreaterEqual(int(score["score"]), 80)

    def test_checkpoint_blocking_when_drift_fails(self) -> None:
        state_store: dict[str, dict[str, object]] = {}
        now_counter = {"value": 0}

        def _now() -> str:
            now_counter["value"] += 1
            return f"2026-01-01T00:00:{now_counter['value']:02d}+00:00"

        def _read(slug: str) -> dict[str, object]:
            return dict(state_store.get(slug, {}))

        def _write(slug: str, payload: dict[str, object]) -> None:
            state_store[slug] = dict(payload)

        def _ok(_args: object) -> int:
            return 0

        def _drift_fail(_args: object) -> int:
            return 1

        with tempfile.TemporaryDirectory() as tmp:
            report_root = Path(tmp)
            plan_path = report_root / "softos-quality-gates-traceability-and-risk.json"
            plan_path.write_text(
                json.dumps({"slices": [{"name": "core", "repo": "r1", "owned_targets": ["backend/core.py"]}]}, ensure_ascii=True),
                encoding="utf-8",
            )
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = workflows.command_workflow_run(
                    type(
                        "Args",
                        (),
                        {
                            "spec": "softos-quality-gates-traceability-and-risk",
                            "resume_from_stage": "",
                            "retry_stage": "",
                            "pause_at_stage": "",
                            "json": True,
                            "orchestrator": "bmad",
                            "force_orchestrator": False,
                        },
                    )(),
                    require_dirs=lambda: None,
                    workspace_config={"project": {"workflow": {"default_orchestrator": "bmad", "force_orchestrator": True}}},
                    resolve_spec=lambda value: Path(value),
                    spec_slug=lambda path: path.name,
                    read_state=_read,
                    write_state=_write,
                    command_plan=_ok,
                    command_slice_start=_ok,
                    command_ci_spec=_ok,
                    command_ci_repo=_ok,
                    command_ci_integration=_ok,
                    command_release_promote=_ok,
                    command_release_verify=_ok,
                    command_infra_apply=_ok,
                    command_workflow_execute_feature=_ok,
                    command_drift_check=_drift_fail,
                    command_contract_verify=_ok,
                    command_spec_generate_contracts=_ok,
                    plan_root=report_root,
                    workflow_report_root=report_root,
                    rel=lambda path: str(path),
                    utc_now=_now,
                    json_dumps=lambda obj: json.dumps(obj, ensure_ascii=True),
                )
            self.assertEqual(1, rc)
            payload = json.loads(out.getvalue().strip())
            self.assertEqual("failed", payload["status"])
            self.assertTrue(any(item["checkpoint"] == "drift-check-pass" and item["status"] == "failed" for item in payload["quality_checkpoints"]))

    def test_api_dto_enforcement_fails_without_generated_contracts(self) -> None:
        state_store: dict[str, dict[str, object]] = {}

        def _read(slug: str) -> dict[str, object]:
            return dict(state_store.get(slug, {}))

        def _write(slug: str, payload: dict[str, object]) -> None:
            state_store[slug] = dict(payload)

        def _ok(_args: object) -> int:
            return 0

        def _generate_empty(_args: object) -> int:
            print(json.dumps({"artifacts": [], "findings": []}, ensure_ascii=True))
            return 0

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "softos-quality-gates-traceability-and-risk.json").write_text(
                json.dumps({"slices": [{"name": "api", "repo": "r1", "owned_targets": ["backend/api/orders.py"]}]}, ensure_ascii=True),
                encoding="utf-8",
            )
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = workflows.command_workflow_run(
                    type(
                        "Args",
                        (),
                        {
                            "spec": "softos-quality-gates-traceability-and-risk",
                            "resume_from_stage": "",
                            "retry_stage": "",
                            "pause_at_stage": "",
                            "json": True,
                            "orchestrator": "bmad",
                            "force_orchestrator": False,
                        },
                    )(),
                    require_dirs=lambda: None,
                    workspace_config={"project": {"workflow": {"default_orchestrator": "bmad", "force_orchestrator": True}}},
                    resolve_spec=lambda value: Path(value),
                    spec_slug=lambda path: path.name,
                    read_state=_read,
                    write_state=_write,
                    command_plan=_ok,
                    command_slice_start=_ok,
                    command_ci_spec=_ok,
                    command_ci_repo=_ok,
                    command_ci_integration=_ok,
                    command_release_promote=_ok,
                    command_release_verify=_ok,
                    command_infra_apply=_ok,
                    command_workflow_execute_feature=_ok,
                    command_drift_check=_ok,
                    command_contract_verify=_ok,
                    command_spec_generate_contracts=_generate_empty,
                    plan_root=root,
                    workflow_report_root=root,
                    rel=lambda path: str(path),
                    utc_now=lambda: "2026-01-01T00:00:00+00:00",
                    json_dumps=lambda obj: json.dumps(obj, ensure_ascii=True),
                )
            self.assertEqual(1, rc)
            payload = json.loads(out.getvalue().strip())
            self.assertTrue(
                any(
                    item["checkpoint"] == "generate-contracts-pass" and item["status"] == "failed"
                    for item in payload["quality_checkpoints"]
                )
            )


if __name__ == "__main__":
    unittest.main()
