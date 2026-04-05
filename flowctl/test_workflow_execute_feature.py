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
