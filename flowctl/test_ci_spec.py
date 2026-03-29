from __future__ import annotations

import argparse
import json
from pathlib import Path

from flowctl.ci import command_ci_spec


def _args(*, all_specs: bool = False, changed: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        spec=None,
        all=all_specs,
        changed=changed,
        base=None,
        head=None,
        json=True,
    )


def _analysis_with_status(status: str) -> dict[str, object]:
    return {
        "frontmatter": {"status": status},
        "frontmatter_errors": [],
        "missing_frontmatter": [],
        "target_errors": [],
        "test_errors": [],
        "todo_count": 0,
        "schema_version": 2,
        "target_index": {"sdd-workspace-boilerplate": []},
        "test_index": {"sdd-workspace-boilerplate": []},
    }


def test_ci_spec_all_treats_draft_as_advisory(tmp_path: Path, capsys) -> None:
    spec_path = tmp_path / "specs" / "features" / "demo.spec.md"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text("dummy", encoding="utf-8")

    rc = command_ci_spec(
        _args(all_specs=True),
        require_dirs=lambda: None,
        select_spec_paths=lambda *_args, **_kwargs: [spec_path],
        analyze_spec=lambda _path: _analysis_with_status("draft"),
        test_reference_findings=lambda _analysis: [],
        repos_missing_test_refs=lambda _a, _b: [],
        spec_dependency_findings=lambda _analysis: [],
        rel=lambda p: str(p),
        format_findings=lambda items: [f"- {item}" for item in items] if items else ["- Sin hallazgos."],
        slugify=lambda value: str(value).replace("/", "-"),
        write_json=lambda path, payload: path.write_text(json.dumps(payload), encoding="utf-8"),
        ci_report_root=tmp_path,
        utc_now=lambda: "2026-01-01T00:00:00+00:00",
        json_dumps=lambda obj: json.dumps(obj),
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["items"][0]["status"] == "skipped"
    assert any("modo `--all` o `--changed`" in str(item) for item in payload["items"][0]["findings"])


def test_ci_spec_changed_treats_draft_as_skipped(tmp_path: Path, capsys) -> None:
    spec_path = tmp_path / "specs" / "features" / "demo.spec.md"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text("dummy", encoding="utf-8")

    rc = command_ci_spec(
        _args(all_specs=False, changed=True),
        require_dirs=lambda: None,
        select_spec_paths=lambda *_args, **_kwargs: [spec_path],
        analyze_spec=lambda _path: _analysis_with_status("draft"),
        test_reference_findings=lambda _analysis: [],
        repos_missing_test_refs=lambda _a, _b: [],
        spec_dependency_findings=lambda _analysis: [],
        rel=lambda p: str(p),
        format_findings=lambda items: [f"- {item}" for item in items] if items else ["- Sin hallazgos."],
        slugify=lambda value: str(value).replace("/", "-"),
        write_json=lambda path, payload: path.write_text(json.dumps(payload), encoding="utf-8"),
        ci_report_root=tmp_path,
        utc_now=lambda: "2026-01-01T00:00:00+00:00",
        json_dumps=lambda obj: json.dumps(obj),
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["items"][0]["status"] == "skipped"


def test_ci_spec_single_still_fails_draft(tmp_path: Path, capsys) -> None:
    spec_path = tmp_path / "specs" / "features" / "demo.spec.md"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text("dummy", encoding="utf-8")

    rc = command_ci_spec(
        _args(all_specs=False),
        require_dirs=lambda: None,
        select_spec_paths=lambda *_args, **_kwargs: [spec_path],
        analyze_spec=lambda _path: _analysis_with_status("draft"),
        test_reference_findings=lambda _analysis: [],
        repos_missing_test_refs=lambda _a, _b: [],
        spec_dependency_findings=lambda _analysis: [],
        rel=lambda p: str(p),
        format_findings=lambda items: [f"- {item}" for item in items] if items else ["- Sin hallazgos."],
        slugify=lambda value: str(value).replace("/", "-"),
        write_json=lambda path, payload: path.write_text(json.dumps(payload), encoding="utf-8"),
        ci_report_root=tmp_path,
        utc_now=lambda: "2026-01-01T00:00:00+00:00",
        json_dumps=lambda obj: json.dumps(obj),
    )
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["items"][0]["status"] == "failed"
    assert any("estado `approved`" in str(item) for item in payload["items"][0]["findings"])


def test_ci_spec_all_accepts_released(tmp_path: Path, capsys) -> None:
    spec_path = tmp_path / "specs" / "features" / "demo.spec.md"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text("dummy", encoding="utf-8")

    rc = command_ci_spec(
        _args(all_specs=True),
        require_dirs=lambda: None,
        select_spec_paths=lambda *_args, **_kwargs: [spec_path],
        analyze_spec=lambda _path: _analysis_with_status("released"),
        test_reference_findings=lambda _analysis: [],
        repos_missing_test_refs=lambda _a, _b: [],
        spec_dependency_findings=lambda _analysis: [],
        rel=lambda p: str(p),
        format_findings=lambda items: [f"- {item}" for item in items] if items else ["- Sin hallazgos."],
        slugify=lambda value: str(value).replace("/", "-"),
        write_json=lambda path, payload: path.write_text(json.dumps(payload), encoding="utf-8"),
        ci_report_root=tmp_path,
        utc_now=lambda: "2026-01-01T00:00:00+00:00",
        json_dumps=lambda obj: json.dumps(obj),
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["items"][0]["status"] == "passed"
