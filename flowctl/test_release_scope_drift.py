from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from flowctl import release


def _write_plan(root: Path) -> Path:
    plan_root = root / ".flow" / "plans"
    plan_root.mkdir(parents=True)
    (plan_root / "demo.json").write_text(
        json.dumps(
            {
                "feature": "demo",
                "slices": [
                    {
                        "name": "core",
                        "repo": "root",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return plan_root


def _analysis() -> dict[str, object]:
    return {
        "target_index": {
            "root": [
                {"relative": "flowctl/**"},
            ]
        },
        "test_index": {
            "root": [
                {"relative": "flowctl/test_*.py"},
            ]
        },
    }


def test_release_scope_drift_passes_when_verified_changes_match_targets(tmp_path: Path) -> None:
    findings = release._release_scope_drift_findings(
        "demo",
        {
            "slice_results": {
                "core": {
                    "status": "passed",
                    "repo": "root",
                    "changed_files": ["flowctl/release.py", "flowctl/test_release_scope_drift.py"],
                }
            }
        },
        _analysis(),
        plan_root=_write_plan(tmp_path),
        root=tmp_path,
        rel=lambda path: str(path.relative_to(tmp_path)),
    )

    assert findings == []


def test_release_scope_drift_blocks_files_outside_approved_targets(tmp_path: Path) -> None:
    findings = release._release_scope_drift_findings(
        "demo",
        {
            "slice_results": {
                "core": {
                    "status": "passed",
                    "repo": "root",
                    "changed_files": ["docs/unplanned.md"],
                }
            }
        },
        _analysis(),
        plan_root=_write_plan(tmp_path),
        root=tmp_path,
        rel=lambda path: str(path.relative_to(tmp_path)),
    )

    assert findings == ["La slice `core` cambio `root:docs/unplanned.md` fuera de targets/tests aprobados."]


def test_release_scope_drift_blocks_legacy_verification_without_changed_files(tmp_path: Path) -> None:
    findings = release._release_scope_drift_findings(
        "demo",
        {
            "slice_results": {
                "core": {
                    "status": "passed",
                    "repo": "root",
                    "report": ".flow/reports/demo-core-verification.md",
                }
            }
        },
        _analysis(),
        plan_root=_write_plan(tmp_path),
        root=tmp_path,
        rel=lambda path: str(path.relative_to(tmp_path)),
    )

    assert findings == ["La slice `core` fue verificada sin inventario `changed_files`; vuelve a ejecutar `slice verify`."]


def test_release_cut_blocks_scope_drift_before_manifest_creation(tmp_path: Path) -> None:
    spec_path = tmp_path / "specs" / "features" / "demo.spec.md"
    spec_path.parent.mkdir(parents=True)
    spec_path.write_text("---\nstatus: approved\n---\n# Demo\n", encoding="utf-8")
    report_path = tmp_path / ".flow" / "reports" / "demo-core-verification.md"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("# report\n", encoding="utf-8")
    manifest_root = tmp_path / "releases" / "manifests"
    manifest_root.mkdir(parents=True)

    try:
        release.command_release_cut(
            Namespace(version="v2026.04.17-test", force=False, spec=["demo"], all_approved=False, json=True),
            require_dirs=lambda: None,
            release_default_version=lambda: "v2026.04.17-default",
            release_manifest_path=lambda version: manifest_root / f"{version}.json",
            resolve_spec=lambda _identifier: spec_path,
            releasable_feature_specs=lambda: [],
            ensure_spec_ready_for_approval=lambda _path: {
                "frontmatter": {"status": "approved"},
                "target_index": {"root": [{"relative": "flowctl/**"}]},
                "test_index": {"root": []},
                "targets": ["../../flowctl/**"],
                "test_refs": [],
                "verification_matrix": [],
            },
            rel=lambda path: str(path.relative_to(tmp_path)),
            spec_slug=lambda _path: "demo",
            read_state=lambda _slug: {
                "status": "in-review",
                "slice_results": {
                    "core": {
                        "status": "passed",
                        "repo": "root",
                        "report": ".flow/reports/demo-core-verification.md",
                        "changed_files": ["docs/unplanned.md"],
                    }
                },
            },
            root=tmp_path,
            root_repo="root",
            workspace_config={"repos": {}},
            plan_root=_write_plan(tmp_path),
            git_changed_files=lambda _path: ([], None),
            repo_head_sha=lambda _repo: "abc123",
            repo_root=lambda _repo: tmp_path,
            release_manifest_root=manifest_root,
            utc_now=lambda: "2026-04-17T00:00:00+00:00",
            write_json=lambda path, payload: path.write_text(json.dumps(payload), encoding="utf-8"),
            write_state=lambda _slug, _state: None,
            json_dumps=lambda payload: json.dumps(payload),
        )
    except SystemExit as exc:
        assert "scope drift antes de release" in str(exc)
    else:
        raise AssertionError("release cut should block scope drift")

    assert not (manifest_root / "v2026.04.17-test.json").exists()
