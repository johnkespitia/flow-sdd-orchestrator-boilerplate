from __future__ import annotations

import json
from pathlib import Path

from flowctl import admin


def _capture_factory(status_by_path: dict[str, str], branch_by_path: dict[str, str]):
    def _capture(command: list[str], cwd: Path) -> dict[str, object]:
        path = str(Path(command[2]).resolve()) if len(command) > 2 else str(cwd.resolve())
        if command[-2:] == ["branch", "--show-current"]:
            return {
                "command": command,
                "returncode": 0,
                "output_tail": branch_by_path.get(path, ""),
            }
        if command[-2:] == ["status", "--porcelain"]:
            return {
                "command": command,
                "returncode": 0,
                "output_tail": status_by_path.get(path, ""),
            }
        return {"command": command, "returncode": 0, "output_tail": ""}

    return _capture


def test_build_worktree_inventory_classifies_active_closed_and_orphan(tmp_path: Path) -> None:
    worktree_root = tmp_path / ".worktrees"
    plan_root = tmp_path / ".flow" / "plans"
    state_root = tmp_path / ".flow" / "state"
    worktree_root.mkdir(parents=True)
    plan_root.mkdir(parents=True)
    state_root.mkdir(parents=True)

    active = worktree_root / "api-feature-slice-a"
    closed = worktree_root / "api-feature-slice-b"
    orphan = worktree_root / "orphan-clean"
    for path in (active, closed, orphan):
        path.mkdir()
        (path / ".git").write_text("gitdir: /tmp/demo\n", encoding="utf-8")

    plan_payload = {
        "feature": "feature-demo",
        "slices": [
            {"name": "slice-a", "repo": "api", "branch": "feat/demo-a", "worktree": str(active)},
            {"name": "slice-b", "repo": "api", "branch": "feat/demo-b", "worktree": str(closed)},
        ],
    }
    (plan_root / "feature-demo.json").write_text(json.dumps(plan_payload), encoding="utf-8")
    state_payload = {
        "status": "slice-started",
        "slice_results": {
            "slice-a": {"status": "started"},
            "slice-b": {"status": "passed"},
        },
    }
    (state_root / "feature-demo.json").write_text(json.dumps(state_payload), encoding="utf-8")

    capture = _capture_factory(
        status_by_path={
            str(active.resolve()): "",
            str(closed.resolve()): "",
            str(orphan.resolve()): "",
        },
        branch_by_path={
            str(active.resolve()): "feat/demo-a",
            str(closed.resolve()): "feat/demo-b",
            str(orphan.resolve()): "demo/orphan-clean",
        },
    )

    inventory = admin._build_worktree_inventory(
        repo_names=["api", "sdd-workspace-boilerplate"],
        root_repo="sdd-workspace-boilerplate",
        worktree_root=worktree_root,
        plan_root=plan_root,
        state_root=state_root,
        capture_command=capture,
    )

    by_name = {item["name"]: item for item in inventory}
    assert by_name["api-feature-slice-a"]["activity"] == "active"
    assert by_name["api-feature-slice-a"]["cleanable"] is False
    assert by_name["api-feature-slice-b"]["activity"] == "closed"
    assert by_name["api-feature-slice-b"]["cleanable"] is True
    assert by_name["orphan-clean"]["activity"] == "orphan"
    assert by_name["orphan-clean"]["cleanable"] is True


def test_select_worktrees_for_cleanup_preserves_dirty_without_force() -> None:
    inventory = [
        {
            "name": "active-clean",
            "activity": "active",
            "dirty": False,
            "cleanable": False,
            "reason": "active-plan",
            "plan_refs": [{"feature": "demo"}],
        },
        {
            "name": "closed-dirty",
            "activity": "closed",
            "dirty": True,
            "cleanable": False,
            "reason": "dirty",
            "plan_refs": [{"feature": "demo"}],
        },
        {
            "name": "closed-clean",
            "activity": "closed",
            "dirty": False,
            "cleanable": True,
            "reason": "closed-clean",
            "plan_refs": [{"feature": "demo"}],
        },
    ]

    selected, findings = admin._select_worktrees_for_cleanup(
        inventory,
        names=set(),
        features=set(),
        stale_only=True,
        force=False,
    )

    assert [item["name"] for item in selected] == ["closed-clean"]
    assert any("active-clean" in finding for finding in findings)
    assert any("closed-dirty" in finding for finding in findings)
