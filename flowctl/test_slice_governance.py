from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pytest

from flowctl.features import command_plan
from flowctl.specs import (
    SpecConfig,
    analyze_spec,
    build_spec_config,
    require_routed_paths,
    slice_governance_findings,
)
from flowctl.workflows import command_workflow_next_step


def _config(tmp_path: Path) -> SpecConfig:
    return build_spec_config(
        root=tmp_path,
        specs_root=tmp_path / "specs",
        feature_specs=tmp_path / "specs" / "features",
        root_repo="root",
        default_targets={"root": ["../../specs/**"], "api": ["../../api/app/**", "../../api/tests/**"]},
        repo_prefixes={"api": "../../api/", "root": "../../"},
        target_roots={"root": {"specs"}, "api": {"app", "tests"}},
        test_required_roots={"root": set(), "api": {"app", "tests"}},
        test_hints={"api": "../../api/tests/**"},
        required_frontmatter_fields=("name", "description", "status", "targets"),
        test_ref_re=re.compile(r"\[@test\]\s+([^\s`]+)"),
        todo_re=re.compile(r"\bTODO\b"),
    )


def _write_spec(tmp_path: Path, body: str) -> Path:
    spec_path = tmp_path / "specs" / "features" / "demo.spec.md"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(body, encoding="utf-8")
    return spec_path


def test_slice_breakdown_supports_multi_slice_plan(tmp_path: Path) -> None:
    config = _config(tmp_path)
    spec_path = _write_spec(
        tmp_path,
        """---
schema_version: 3
name: demo
description: demo
status: approved
owner: platform
single_slice_reason: ""
multi_domain: false
phases: []
depends_on: []
required_runtimes: []
required_services: []
required_capabilities: []
stack_projects: []
stack_services: []
stack_capabilities: []
targets:
  - ../../api/app/controllers/**
  - ../../api/app/services/**
---

# demo

## Slice Breakdown

```yaml
- name: api-controller
  targets:
    - ../../api/app/controllers/**
  hot_area: api/controllers
  depends_on: []
- name: api-service
  targets:
    - ../../api/app/services/**
  hot_area: api/services
  depends_on:
    - api-controller
```
""",
    )

    analysis = analyze_spec(spec_path, config=config)

    assert len(analysis["slice_breakdown"]) == 2
    assert analysis["slice_breakdown"][1]["depends_on"] == ["api-controller"]
    assert slice_governance_findings(analysis) == []


def test_slice_governance_requires_exception_for_single_slice(tmp_path: Path) -> None:
    config = _config(tmp_path)
    spec_path = _write_spec(
        tmp_path,
        """---
schema_version: 3
name: demo
description: demo
status: approved
owner: platform
single_slice_reason: ""
multi_domain: true
phases:
  - foundation
  - rollout
depends_on: []
required_runtimes: []
required_services: []
required_capabilities: []
stack_projects: []
stack_services: []
stack_capabilities: []
targets:
  - ../../api/app/controllers/**
---

# demo

## Slice Breakdown

```yaml
- name: api-main
  targets:
    - ../../api/app/controllers/**
  hot_area: api/controllers
  depends_on: []
```
""",
    )

    analysis = analyze_spec(spec_path, config=config)
    findings = slice_governance_findings(analysis)

    assert any("single_slice_reason" in item for item in findings)
    assert any("al menos `3`" in item or "al menos `2`" in item for item in findings)


def test_command_plan_materializes_declared_slices(tmp_path: Path) -> None:
    config = _config(tmp_path)
    spec_path = _write_spec(
        tmp_path,
        """---
schema_version: 3
name: demo
description: demo
status: approved
owner: platform
single_slice_reason: ""
multi_domain: false
phases: []
depends_on: []
required_runtimes: []
required_services: []
required_capabilities: []
stack_projects: []
stack_services: []
stack_capabilities: []
targets:
  - ../../api/app/controllers/**
  - ../../api/app/services/**
---

# demo

## Slice Breakdown

```yaml
- name: api-controller
  targets:
    - ../../api/app/controllers/**
  hot_area: api/controllers
  depends_on: []
- name: api-service
  targets:
    - ../../api/app/services/**
  hot_area: api/services
  depends_on:
    - api-controller
```
""",
    )
    (tmp_path / "api").mkdir(parents=True, exist_ok=True)
    plan_root = tmp_path / ".flow" / "plans"
    worktree_root = tmp_path / ".worktrees"
    state: dict[str, object] = {}

    rc = command_plan(
        argparse.Namespace(spec="demo"),
        require_dirs=lambda: plan_root.mkdir(parents=True, exist_ok=True),
        resolve_spec=lambda _spec: spec_path,
        spec_slug=lambda _path: "demo",
        analyze_spec=lambda path: analyze_spec(path, config=config),
        require_routed_paths=lambda paths, label: require_routed_paths(paths, label, config=config),
        repo_slice_prefix=lambda repo: repo,
        repo_root=lambda repo: tmp_path / repo,
        worktree_root=worktree_root,
        plan_root=plan_root,
        read_state=lambda _slug: state.copy(),
        write_state=lambda _slug, payload: state.update(payload),
        rel=lambda path: str(path),
        utc_now=lambda: "2026-03-29T00:00:00+00:00",
    )

    assert rc == 0
    payload = json.loads((plan_root / "demo.json").read_text(encoding="utf-8"))
    assert [item["name"] for item in payload["slices"]] == ["api-controller", "api-service"]
    assert payload["slices"][0]["hot_area"] == "api/controllers"
    assert payload["slices"][1]["depends_on"] == ["api-controller"]


def test_workflow_next_step_blocks_invalid_slice_governance(tmp_path: Path) -> None:
    spec_path = _write_spec(tmp_path, "# demo\n")
    analysis = {
        "frontmatter": {"status": "approved"},
        "schema_version": 3,
        "targets": ["../../api/app/controllers/**"],
        "target_index": {"api": [{"raw": "../../api/app/controllers/**", "relative": "app/controllers/**"}]},
        "slice_breakdown": [],
        "slice_breakdown_errors": ["Falta la seccion `## Slice Breakdown` con un bloque YAML."],
        "single_slice_reason": "",
        "multi_domain": False,
        "phases": [],
    }

    with pytest.raises(SystemExit, match="gobernanza de slices"):
        command_workflow_next_step(
            argparse.Namespace(spec="demo", json=True),
            require_dirs=lambda: None,
            workspace_config={"project": {"workflow": {"default_orchestrator": "bmad", "force_orchestrator": True}}},
            resolve_spec=lambda _spec: spec_path,
            spec_slug=lambda _path: "demo",
            analyze_spec=lambda _path: analysis,
            read_state=lambda _slug: {},
            plan_root=tmp_path / ".flow" / "plans",
            workflow_report_root=tmp_path / ".flow" / "reports" / "workflow",
            root=tmp_path,
            rel=lambda path: str(path),
            utc_now=lambda: "2026-03-29T00:00:00+00:00",
            json_dumps=json.dumps,
        )
