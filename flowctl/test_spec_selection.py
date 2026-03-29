from __future__ import annotations

from pathlib import Path

from flowctl.specs import build_spec_config, select_spec_paths


def test_select_spec_paths_changed_ignores_templates_outside_specs_root(tmp_path: Path) -> None:
    specs_root = tmp_path / "specs"
    feature_specs = specs_root / "features"
    feature_specs.mkdir(parents=True, exist_ok=True)
    real_spec = feature_specs / "demo.spec.md"
    real_spec.write_text("ok", encoding="utf-8")

    template_spec = tmp_path / "templates" / "root-feature.spec.md"
    template_spec.parent.mkdir(parents=True, exist_ok=True)
    template_spec.write_text("template", encoding="utf-8")

    config = build_spec_config(
        root=tmp_path,
        specs_root=specs_root,
        feature_specs=feature_specs,
        root_repo="root",
        default_targets={"root": ["../../specs/**"]},
        repo_prefixes={"root": "../../"},
        target_roots={"root": {"specs"}},
        test_required_roots={"root": set()},
        test_hints={},
        required_frontmatter_fields=("name", "description", "status", "targets"),
        test_ref_re=__import__("re").compile(r"\[@test\]\s+([^\s`]+)"),
        todo_re=__import__("re").compile(r"\bTODO\b"),
    )

    selected = select_spec_paths(
        config=config,
        resolve_spec=lambda identifier: tmp_path / identifier,
        git_diff_name_only=lambda _root, base=None, head=None: (
            ["templates/root-feature.spec.md", "specs/features/demo.spec.md"],
            None,
        ),
        changed=True,
    )

    assert selected == [real_spec.resolve()]
