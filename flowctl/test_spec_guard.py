from __future__ import annotations

import argparse
import json
from pathlib import Path

from flowctl.contracts_ops import command_spec_guard


def _args(*, all_specs: bool = False, changed: bool = False, staged: bool = False, spec: str | None = None) -> argparse.Namespace:
    return argparse.Namespace(
        spec=spec,
        all=all_specs,
        changed=changed,
        staged=staged,
        base="BASE",
        head="HEAD",
        json=True,
    )


def test_spec_guard_fails_when_stable_surfaces_change_without_spec(tmp_path: Path, capsys) -> None:
    rc = command_spec_guard(
        _args(changed=True),
        require_dirs=lambda: None,
        select_spec_paths=lambda *_args, **_kwargs: [],
        root=tmp_path,
        root_repo="root",
        implementation_repos=lambda: [],
        repo_root=lambda repo: tmp_path,
        analyze_spec=lambda _path: {},
        git_diff_name_only=lambda _root, base=None, head=None: (["runtimes/python.runtime.json"], None),
        staged_repo_files_fn=lambda _root: ([], None),
        repo_paths_changed_under_roots=lambda _repo, paths: paths,
        matches_any_pattern=lambda path, patterns: False,
        rel=lambda p: str(p),
        utc_now=lambda: "2026-01-01T00:00:00+00:00",
        json_dumps=lambda obj: json.dumps(obj),
    )
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert any("superficies estables sin cambios de spec" in str(item) for item in payload["findings"])


def test_spec_guard_passes_when_selected_spec_covers_stable_change(tmp_path: Path, capsys) -> None:
    spec_path = tmp_path / "specs" / "features" / "demo.spec.md"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text("demo", encoding="utf-8")

    rc = command_spec_guard(
        _args(changed=True),
        require_dirs=lambda: None,
        select_spec_paths=lambda *_args, **_kwargs: [spec_path],
        root=tmp_path,
        root_repo="root",
        implementation_repos=lambda: [],
        repo_root=lambda repo: tmp_path,
        analyze_spec=lambda _path: {
            "target_index": {
                "root": [
                    {"relative": "runtimes/**"},
                ]
            }
        },
        git_diff_name_only=lambda _root, base=None, head=None: (["runtimes/python.runtime.json"], None),
        staged_repo_files_fn=lambda _root: ([], None),
        repo_paths_changed_under_roots=lambda _repo, paths: paths,
        matches_any_pattern=lambda path, patterns: path.startswith("runtimes/"),
        rel=lambda p: str(p),
        utc_now=lambda: "2026-01-01T00:00:00+00:00",
        json_dumps=lambda obj: json.dumps(obj),
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["findings"] == []


def test_spec_guard_staged_uses_staged_files_for_guard(tmp_path: Path, capsys) -> None:
    spec_path = tmp_path / "specs" / "features" / "demo.spec.md"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text("demo", encoding="utf-8")

    def staged_files(repo_root: Path) -> tuple[list[str], str | None]:
        if repo_root == tmp_path:
            return ["specs/features/demo.spec.md", "workspace.skills.json"], None
        return [], None

    rc = command_spec_guard(
        _args(staged=True),
        require_dirs=lambda: None,
        select_spec_paths=lambda *_args, **_kwargs: [],
        root=tmp_path,
        root_repo="root",
        implementation_repos=lambda: [],
        repo_root=lambda repo: tmp_path,
        analyze_spec=lambda _path: {
            "target_index": {
                "root": [
                    {"relative": "workspace.skills.json"},
                ]
            }
        },
        git_diff_name_only=lambda _root, base=None, head=None: ([], None),
        staged_repo_files_fn=staged_files,
        repo_paths_changed_under_roots=lambda _repo, paths: paths,
        matches_any_pattern=lambda path, patterns: path == "workspace.skills.json",
        rel=lambda p: str(p),
        utc_now=lambda: "2026-01-01T00:00:00+00:00",
        json_dumps=lambda obj: json.dumps(obj),
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["scope"] == "staged"
