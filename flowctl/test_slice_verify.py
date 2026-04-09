from __future__ import annotations

from pathlib import Path

import json

from flowctl.features import resolve_slice_inspection_path, update_plan_slice_status


def test_resolve_slice_inspection_path_uses_worktree_root_for_direct_checkout(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    repo_path = root / "zsdmsistema-dev"
    planned_worktree = tmp_path / ".worktrees" / "zsdmsistema-dev-demo-main"
    root.mkdir(parents=True)
    repo_path.mkdir()
    planned_worktree.mkdir(parents=True)
    (planned_worktree / ".git").write_text("gitdir: /tmp/demo\n", encoding="utf-8")

    resolved = resolve_slice_inspection_path(
        repo_path=repo_path,
        planned_worktree=planned_worktree,
        root=root,
    )

    assert resolved == planned_worktree


def test_resolve_slice_inspection_path_uses_nested_repo_when_present(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    repo_path = root / "zsdmsistema-dev"
    planned_worktree = tmp_path / ".worktrees" / "zsdmsistema-dev-demo-main"
    nested_repo = planned_worktree / "zsdmsistema-dev"
    root.mkdir(parents=True)
    repo_path.mkdir()
    nested_repo.mkdir(parents=True)

    resolved = resolve_slice_inspection_path(
        repo_path=repo_path,
        planned_worktree=planned_worktree,
        root=root,
    )

    assert resolved == nested_repo


def test_resolve_slice_inspection_path_falls_back_to_repo_without_worktree(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    repo_path = root / "zsdmsistema-dev"
    planned_worktree = tmp_path / ".worktrees" / "missing-worktree"
    root.mkdir(parents=True)
    repo_path.mkdir()

    resolved = resolve_slice_inspection_path(
        repo_path=repo_path,
        planned_worktree=planned_worktree,
        root=root,
    )

    assert resolved == repo_path


def test_update_plan_slice_status_persists_verification_result(tmp_path: Path) -> None:
    plan_root = tmp_path / ".flow" / "plans"
    plan_root.mkdir(parents=True)
    plan_path = plan_root / "demo.json"
    plan_path.write_text(
        json.dumps({"feature": "demo", "slices": [{"name": "demo-slice", "status": "slice-ready"}]}),
        encoding="utf-8",
    )

    update_plan_slice_status(
        plan_root=plan_root,
        slug="demo",
        slice_name="demo-slice",
        status="verification-passed",
        extra={"last_verification_result": "passed"},
    )

    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    assert payload["slices"][0]["status"] == "verification-passed"
    assert payload["slices"][0]["last_verification_result"] == "passed"
