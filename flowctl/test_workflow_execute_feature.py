from __future__ import annotations

import io
import json
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

from flowctl import workflows


def test_execute_feature_attaches_auto_worktree_cleanup_payload() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        plan_root = root / ".flow" / "plans"
        report_root = root / ".flow" / "reports" / "workflows"
        plan_root.mkdir(parents=True)
        report_root.mkdir(parents=True)

        plan_payload = {
            "feature": "demo-feature",
            "slices": [
                {
                    "name": "root-main",
                    "repo": "sdd-workspace-boilerplate",
                    "branch": "feat/demo-feature-root-main",
                    "worktree": str(root / ".worktrees" / "demo-feature-root-main"),
                    "executor_mode": "implementation",
                }
            ],
        }
        (plan_root / "demo-feature.json").write_text(json.dumps(plan_payload), encoding="utf-8")

        args = type(
            "Args",
            (),
            {
                "spec": "demo-feature",
                "refresh_plan": False,
                "start_slices": False,
                "no_worktree_cleanup": False,
                "json": True,
                "orchestrator": "bmad",
                "force_orchestrator": False,
            },
        )()

        out = io.StringIO()
        with redirect_stdout(out):
            rc = workflows.command_workflow_execute_feature(
                args,
                require_dirs=lambda: None,
                workspace_config={"project": {"workflow": {"default_orchestrator": "bmad", "force_orchestrator": True}}},
                resolve_spec=lambda value: Path(value),
                spec_slug=lambda path: path.name,
                analyze_spec=lambda path: {
                    "frontmatter": {"status": "approved"},
                    "target_index": {"sdd-workspace-boilerplate": []},
                },
                plan_root=plan_root,
                workflow_report_root=report_root,
                plan_callable=lambda _args: 0,
                slice_start_callable=lambda _args: 0,
                root=root,
                rel=lambda path: str(path),
                auto_worktree_cleanup=lambda: {"removed": ["stale-demo"], "findings": []},
                utc_now=lambda: "2026-04-04T00:00:00+00:00",
                json_dumps=lambda payload: json.dumps(payload, ensure_ascii=True),
            )

        assert rc == 0
        payload = json.loads(out.getvalue().strip())
        assert payload["worktree_cleanup"]["removed"] == ["stale-demo"]


def test_execute_feature_can_skip_auto_worktree_cleanup() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        plan_root = root / ".flow" / "plans"
        report_root = root / ".flow" / "reports" / "workflows"
        plan_root.mkdir(parents=True)
        report_root.mkdir(parents=True)

        (plan_root / "demo-feature.json").write_text(
            json.dumps({"feature": "demo-feature", "slices": []}),
            encoding="utf-8",
        )

        args = type(
            "Args",
            (),
            {
                "spec": "demo-feature",
                "refresh_plan": False,
                "start_slices": False,
                "no_worktree_cleanup": True,
                "json": True,
                "orchestrator": "bmad",
                "force_orchestrator": False,
            },
        )()

        out = io.StringIO()
        with redirect_stdout(out):
            rc = workflows.command_workflow_execute_feature(
                args,
                require_dirs=lambda: None,
                workspace_config={"project": {"workflow": {"default_orchestrator": "bmad", "force_orchestrator": True}}},
                resolve_spec=lambda value: Path(value),
                spec_slug=lambda path: path.name,
                analyze_spec=lambda path: {
                    "frontmatter": {"status": "approved"},
                    "target_index": {"sdd-workspace-boilerplate": []},
                },
                plan_root=plan_root,
                workflow_report_root=report_root,
                plan_callable=lambda _args: 0,
                slice_start_callable=lambda _args: 0,
                root=root,
                rel=lambda path: str(path),
                auto_worktree_cleanup=lambda: {"removed": ["stale-demo"], "findings": []},
                utc_now=lambda: "2026-04-04T00:00:00+00:00",
                json_dumps=lambda payload: json.dumps(payload, ensure_ascii=True),
            )

        assert rc == 0
        payload = json.loads(out.getvalue().strip())
        assert "worktree_cleanup" not in payload


def test_workflow_next_step_skips_verified_slices_and_recommends_close_feature() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        plan_root = root / ".flow" / "plans"
        report_root = root / ".flow" / "reports" / "workflows"
        plan_root.mkdir(parents=True)
        report_root.mkdir(parents=True)
        (plan_root / "demo-feature.json").write_text(
            json.dumps(
                {
                    "feature": "demo-feature",
                    "slices": [
                        {"name": "slice-a", "repo": "sdd-workspace-boilerplate", "status": "verification-passed"},
                        {"name": "slice-b", "repo": "sdd-workspace-boilerplate", "status": "verification-passed"},
                    ],
                }
            ),
            encoding="utf-8",
        )

        args = type("Args", (), {"spec": "demo-feature", "json": True, "orchestrator": "bmad", "force_orchestrator": False})()
        out = io.StringIO()
        with redirect_stdout(out):
            rc = workflows.command_workflow_next_step(
                args,
                require_dirs=lambda: None,
                workspace_config={"project": {"workflow": {"default_orchestrator": "bmad", "force_orchestrator": True}}},
                resolve_spec=lambda value: Path(value),
                spec_slug=lambda path: path.name,
                analyze_spec=lambda path: {"frontmatter": {"status": "approved"}, "target_index": {"sdd-workspace-boilerplate": []}},
                read_state=lambda _slug: {"slice_results": {"slice-a": {"status": "passed"}, "slice-b": {"status": "passed"}}},
                plan_root=plan_root,
                workflow_report_root=report_root,
                root=root,
                rel=lambda path: str(path),
                utc_now=lambda: "2026-04-09T00:00:00+00:00",
                json_dumps=lambda payload: json.dumps(payload, ensure_ascii=True),
            )

        assert rc == 0
        payload = json.loads(out.getvalue().strip())
        assert payload["stage"] == "ready-for-merge"
        assert any("close-feature" in command for command in payload["next_commands"])


def test_workflow_close_feature_closes_verified_slices() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        plan_root = root / ".flow" / "plans"
        report_root = root / ".flow" / "reports" / "workflows"
        plan_root.mkdir(parents=True)
        report_root.mkdir(parents=True)
        plan_path = plan_root / "demo-feature.json"
        plan_path.write_text(
            json.dumps(
                {
                    "feature": "demo-feature",
                    "spec_path": "specs/features/demo-feature.spec.md",
                    "slices": [
                        {"name": "slice-a", "repo": "sdd-workspace-boilerplate", "status": "verification-passed"},
                        {"name": "slice-b", "repo": "sdd-workspace-boilerplate", "status": "verification-passed"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        recorded_state: dict[str, object] = {}
        args = type("Args", (), {"spec": "demo-feature", "json": True})()
        out = io.StringIO()
        with redirect_stdout(out):
            rc = workflows.command_workflow_close_feature(
                args,
                require_dirs=lambda: None,
                resolve_spec=lambda value: Path(value),
                spec_slug=lambda path: path.name,
                analyze_spec=lambda path: {"frontmatter": {"status": "approved"}},
                read_state=lambda _slug: {"slice_results": {"slice-a": {"status": "passed"}, "slice-b": {"status": "passed"}}},
                write_state=lambda _slug, payload: recorded_state.update(payload),
                plan_root=plan_root,
                workflow_report_root=report_root,
                rel=lambda path: str(path),
                utc_now=lambda: "2026-04-09T00:00:00+00:00",
                json_dumps=lambda payload: json.dumps(payload, ensure_ascii=True),
            )

        assert rc == 0
        payload = json.loads(out.getvalue().strip())
        assert payload["state_status"] == "ready-for-merge"
        updated_plan = json.loads(plan_path.read_text(encoding="utf-8"))
        assert all(item["status"] == "closed" for item in updated_plan["slices"])
