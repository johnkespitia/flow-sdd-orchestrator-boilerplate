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


def _rel_to_root(root: Path):
    def rel(path: Path) -> str:
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            return str(path).replace("\\", "/")

    return rel


def _run_spec_guard(
    tmp_path: Path,
    *,
    changed: bool = False,
    staged: bool = False,
    select_spec_paths,
    analyze_spec,
    git_diff_name_only,
    staged_repo_files_fn,
    matches_any_pattern,
    implementation_repos=None,
    repo_paths_changed_under_roots=None,
    path_exists_in_head_fn=None,
    path_exists_in_revision_fn=None,
):
    return command_spec_guard(
        _args(changed=changed, staged=staged),
        require_dirs=lambda: None,
        select_spec_paths=select_spec_paths,
        root=tmp_path,
        root_repo="root",
        implementation_repos=implementation_repos or (lambda: []),
        repo_root=lambda repo: tmp_path,
        analyze_spec=analyze_spec,
        git_diff_name_only=git_diff_name_only,
        staged_repo_files_fn=staged_repo_files_fn,
        repo_paths_changed_under_roots=repo_paths_changed_under_roots or (lambda _repo, paths: paths),
        matches_any_pattern=matches_any_pattern,
        rel=_rel_to_root(tmp_path),
        utc_now=lambda: "2026-01-01T00:00:00+00:00",
        json_dumps=lambda obj: json.dumps(obj),
        path_exists_in_head_fn=path_exists_in_head_fn,
        path_exists_in_revision_fn=path_exists_in_revision_fn,
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


def test_spec_guard_changed_fallback_passes_with_approved_base_spec(tmp_path: Path, capsys) -> None:
    spec_path = tmp_path / "specs" / "features" / "demo.spec.md"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text("demo", encoding="utf-8")

    rc = _run_spec_guard(
        tmp_path,
        changed=True,
        select_spec_paths=lambda *_args, **kwargs: [spec_path] if kwargs.get("all_specs") else [],
        analyze_spec=lambda _path: {
            "frontmatter": {"status": "approved"},
            "target_index": {"root": [{"relative": "opencode.json"}]},
        },
        git_diff_name_only=lambda _root, base=None, head=None: (["opencode.json"], None),
        staged_repo_files_fn=lambda _root: ([], None),
        matches_any_pattern=lambda path, patterns: path == "opencode.json" and "opencode.json" in patterns,
        path_exists_in_revision_fn=lambda _root, path, revision: path == "specs/features/demo.spec.md" and revision == "BASE",
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["findings"] == []
    assert payload["items"][0]["spec"] == "specs/features/demo.spec.md"


def test_spec_guard_changed_fallback_rejects_zero_and_partial_coverage(tmp_path: Path, capsys) -> None:
    spec_path = tmp_path / "specs" / "features" / "demo.spec.md"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text("demo", encoding="utf-8")

    def run(changes: list[str]) -> dict[str, object]:
        rc = _run_spec_guard(
            tmp_path,
            changed=True,
            select_spec_paths=lambda *_args, **kwargs: [spec_path] if kwargs.get("all_specs") else [],
            analyze_spec=lambda _path: {
                "frontmatter": {"status": "approved"},
                "target_index": {"root": [{"relative": "opencode.json"}]},
            },
            git_diff_name_only=lambda _root, base=None, head=None: (changes, None),
            staged_repo_files_fn=lambda _root: ([], None),
            matches_any_pattern=lambda path, patterns: path in patterns,
            path_exists_in_revision_fn=lambda _root, path, revision: True,
        )
        assert rc == 1
        return json.loads(capsys.readouterr().out)

    payload = run(["other.json"])
    assert any("superficies estables sin cambios de spec" in str(item) for item in payload["findings"])

    payload = run(["opencode.json", "other.json"])
    assert any("superficies estables sin cambios de spec" in str(item) for item in payload["findings"])


def test_spec_guard_changed_fallback_accepts_multiple_exact_approved_specs(tmp_path: Path, capsys) -> None:
    spec_a = tmp_path / "specs" / "features" / "alpha.spec.md"
    spec_b = tmp_path / "specs" / "features" / "beta.spec.md"
    spec_a.parent.mkdir(parents=True, exist_ok=True)
    spec_a.write_text("alpha", encoding="utf-8")
    spec_b.write_text("beta", encoding="utf-8")

    rc = _run_spec_guard(
        tmp_path,
        changed=True,
        select_spec_paths=lambda *_args, **kwargs: [spec_a, spec_b] if kwargs.get("all_specs") else [],
        analyze_spec=lambda _path: {
            "frontmatter": {"status": "approved"},
            "target_index": {"root": [{"relative": "opencode.json"}]},
        },
        git_diff_name_only=lambda _root, base=None, head=None: (["opencode.json"], None),
        staged_repo_files_fn=lambda _root: ([], None),
        matches_any_pattern=lambda path, patterns: path in patterns,
        path_exists_in_revision_fn=lambda _root, path, revision: True,
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["findings"] == []
    assert [item["spec"] for item in payload["items"]] == [
        "specs/features/alpha.spec.md",
        "specs/features/beta.spec.md",
    ]


def test_spec_guard_changed_preserves_non_sensitive_behavior(tmp_path: Path, capsys) -> None:
    rc = _run_spec_guard(
        tmp_path,
        changed=True,
        select_spec_paths=lambda *_args, **_kwargs: [],
        analyze_spec=lambda _path: {},
        git_diff_name_only=lambda _root, base=None, head=None: (["docs/example.md"], None),
        staged_repo_files_fn=lambda _root: ([], None),
        matches_any_pattern=lambda _path, _patterns: False,
    )
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["findings"] == []


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


def test_spec_guard_staged_fallback_passes_with_committed_approved_spec(tmp_path: Path, capsys) -> None:
    spec_path = tmp_path / "specs" / "features" / "demo.spec.md"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text("demo", encoding="utf-8")

    def staged_files(repo_root: Path) -> tuple[list[str], str | None]:
        if repo_root == tmp_path:
            return ["opencode.json"], None
        return [], None

    rc = _run_spec_guard(
        tmp_path,
        staged=True,
        select_spec_paths=lambda *_args, **_kwargs: [spec_path],
        analyze_spec=lambda _path: {
            "frontmatter": {"status": "approved"},
            "target_index": {
                "root": [
                    {"relative": "opencode.json"},
                ]
            },
        },
        git_diff_name_only=lambda _root, base=None, head=None: ([], None),
        staged_repo_files_fn=staged_files,
        matches_any_pattern=lambda path, patterns: path == "opencode.json",
        path_exists_in_head_fn=lambda _root, path: path == "specs/features/demo.spec.md",
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["findings"] == []
    assert payload["items"][0]["spec"] == "specs/features/demo.spec.md"
    assert payload["items"][0]["status"] == "passed"


def test_spec_guard_staged_fallback_fails_when_spec_covers_only_some_changes(tmp_path: Path, capsys) -> None:
    spec_path = tmp_path / "specs" / "features" / "demo.spec.md"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text("demo", encoding="utf-8")

    def staged_files(repo_root: Path) -> tuple[list[str], str | None]:
        if repo_root == tmp_path:
            return ["opencode.json", "runtimes/python.runtime.json"], None
        return [], None

    rc = _run_spec_guard(
        tmp_path,
        staged=True,
        select_spec_paths=lambda *_args, **_kwargs: [spec_path],
        analyze_spec=lambda _path: {
            "frontmatter": {"status": "approved"},
            "target_index": {
                "root": [
                    {"relative": "opencode.json"},
                ]
            },
        },
        git_diff_name_only=lambda _root, base=None, head=None: ([], None),
        staged_repo_files_fn=staged_files,
        matches_any_pattern=lambda path, patterns: path == "opencode.json",
    )
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert any("superficies estables sin cambios de spec" in str(item) for item in payload["findings"])


def test_spec_guard_staged_fallback_fails_for_unapproved_spec(tmp_path: Path, capsys) -> None:
    spec_path = tmp_path / "specs" / "features" / "demo.spec.md"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text("demo", encoding="utf-8")

    def staged_files(repo_root: Path) -> tuple[list[str], str | None]:
        if repo_root == tmp_path:
            return ["opencode.json"], None
        return [], None

    rc = _run_spec_guard(
        tmp_path,
        staged=True,
        select_spec_paths=lambda *_args, **_kwargs: [spec_path],
        analyze_spec=lambda _path: {
            "frontmatter": {"status": "draft"},
            "target_index": {
                "root": [
                    {"relative": "opencode.json"},
                ]
            },
        },
        git_diff_name_only=lambda _root, base=None, head=None: ([], None),
        staged_repo_files_fn=staged_files,
        matches_any_pattern=lambda path, patterns: path == "opencode.json",
    )
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert any("superficies estables sin cambios de spec" in str(item) for item in payload["findings"])


def test_spec_guard_staged_fallback_fails_when_approved_spec_has_unstaged_changes(tmp_path: Path, capsys) -> None:
    spec_path = tmp_path / "specs" / "features" / "demo.spec.md"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text("demo", encoding="utf-8")

    def staged_files(repo_root: Path) -> tuple[list[str], str | None]:
        if repo_root == tmp_path:
            return ["opencode.json"], None
        return [], None

    rc = _run_spec_guard(
        tmp_path,
        staged=True,
        select_spec_paths=lambda *_args, **_kwargs: [spec_path],
        analyze_spec=lambda _path: {
            "frontmatter": {"status": "approved"},
            "target_index": {
                "root": [
                    {"relative": "opencode.json"},
                ]
            },
        },
        git_diff_name_only=lambda _root, base=None, head=None: (["specs/features/demo.spec.md"], None),
        staged_repo_files_fn=staged_files,
        matches_any_pattern=lambda path, patterns: path == "opencode.json",
    )
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert any("superficies estables sin cambios de spec" in str(item) for item in payload["findings"])


def test_spec_guard_staged_fallback_fails_with_ambiguous_covering_specs(tmp_path: Path, capsys) -> None:
    spec_a = tmp_path / "specs" / "features" / "alpha.spec.md"
    spec_b = tmp_path / "specs" / "features" / "beta.spec.md"
    spec_a.parent.mkdir(parents=True, exist_ok=True)
    spec_a.write_text("alpha", encoding="utf-8")
    spec_b.write_text("beta", encoding="utf-8")

    def staged_files(repo_root: Path) -> tuple[list[str], str | None]:
        if repo_root == tmp_path:
            return ["opencode.json"], None
        return [], None

    def analyze_spec(path: Path) -> dict[str, object]:
        return {
            "frontmatter": {"status": "approved"},
            "target_index": {
                "root": [
                    {"relative": "opencode.json"},
                ]
            },
        }

    rc = _run_spec_guard(
        tmp_path,
        staged=True,
        select_spec_paths=lambda *_args, **_kwargs: [spec_a, spec_b],
        analyze_spec=analyze_spec,
        git_diff_name_only=lambda _root, base=None, head=None: ([], None),
        staged_repo_files_fn=staged_files,
        matches_any_pattern=lambda path, patterns: path == "opencode.json",
        path_exists_in_head_fn=lambda _root, path: path in {
            "specs/features/alpha.spec.md",
            "specs/features/beta.spec.md",
        },
    )
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert any("Ambiguedad: multiples specs aprobadas cubren los cambios staged" in str(item) for item in payload["findings"])


def test_spec_guard_staged_fallback_preserves_no_candidate_failure(tmp_path: Path, capsys) -> None:
    def staged_files(repo_root: Path) -> tuple[list[str], str | None]:
        if repo_root == tmp_path:
            return ["opencode.json"], None
        return [], None

    rc = _run_spec_guard(
        tmp_path,
        staged=True,
        select_spec_paths=lambda *_args, **_kwargs: [],
        analyze_spec=lambda _path: {},
        git_diff_name_only=lambda _root, base=None, head=None: ([], None),
        staged_repo_files_fn=staged_files,
        matches_any_pattern=lambda path, patterns: False,
    )
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert any("superficies estables sin cambios de spec" in str(item) for item in payload["findings"])


def test_spec_guard_staged_fallback_rejects_untracked_spec_not_in_head(tmp_path: Path, capsys) -> None:
    spec_path = tmp_path / "specs" / "features" / "fake.spec.md"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text("fake", encoding="utf-8")

    def staged_files(repo_root: Path) -> tuple[list[str], str | None]:
        if repo_root == tmp_path:
            return ["opencode.json"], None
        return [], None

    rc = _run_spec_guard(
        tmp_path,
        staged=True,
        select_spec_paths=lambda *_args, **_kwargs: [spec_path],
        analyze_spec=lambda _path: {
            "frontmatter": {"status": "approved"},
            "target_index": {
                "root": [
                    {"relative": "opencode.json"},
                ]
            },
        },
        git_diff_name_only=lambda _root, base=None, head=None: ([], None),
        staged_repo_files_fn=staged_files,
        matches_any_pattern=lambda path, patterns: path == "opencode.json",
        path_exists_in_head_fn=lambda _root, _path: False,
    )
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert any("superficies estables sin cambios de spec" in str(item) for item in payload["findings"])
