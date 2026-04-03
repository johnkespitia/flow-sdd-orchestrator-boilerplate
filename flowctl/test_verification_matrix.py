from __future__ import annotations

import re
from pathlib import Path

from flowctl.specs import (
    SpecConfig,
    analyze_spec,
    build_spec_config,
    verification_matrix_findings,
)


def _config(tmp_path: Path) -> SpecConfig:
    return build_spec_config(
        root=tmp_path,
        specs_root=tmp_path / "specs",
        feature_specs=tmp_path / "specs" / "features",
        root_repo="root",
        default_targets={
            "root": ["../../specs/**"],
            "api": ["../../api/app/**", "../../api/tests/**"],
            "web": ["../../web/src/**", "../../web/tests/**"],
        },
        repo_prefixes={"api": "../../api/", "web": "../../web/", "root": "../../"},
        target_roots={"root": {"specs"}, "api": {"app", "tests"}, "web": {"src", "tests"}},
        test_required_roots={"root": set(), "api": {"app", "tests"}, "web": {"src", "tests"}},
        test_hints={"api": "../../api/tests/**", "web": "../../web/tests/**"},
        required_frontmatter_fields=("name", "description", "status", "targets"),
        test_ref_re=re.compile(r"\[@test\]\s+([^\s`]+)"),
        todo_re=re.compile(r"\bTODO\b"),
    )


def _write_spec(tmp_path: Path, body: str) -> Path:
    spec_path = tmp_path / "specs" / "features" / "verification.spec.md"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(body, encoding="utf-8")
    return spec_path


def test_verification_matrix_is_parsed_from_yaml_block(tmp_path: Path) -> None:
    spec_path = _write_spec(
        tmp_path,
        """---
schema_version: 3
name: verification
description: verification
status: approved
owner: platform
targets:
  - ../../api/app/**
depends_on: []
required_runtimes: []
required_services: []
required_capabilities: []
stack_projects: []
stack_services: []
stack_capabilities: []
single_slice_reason: focused scope
multi_domain: false
phases: []
---

# verification

## Slice Breakdown

```yaml
- name: api-main
  targets:
    - ../../api/app/**
  hot_area: api/app
  depends_on: []
```

## Verification Matrix

```yaml
- name: api-smoke
  level: smoke
  command: scripts/workspace_exec.sh python3 ./flow ci integration --profile smoke --json
  blocking_on:
    - ci
    - release
  environments:
    - staging
```
""",
    )

    analysis = analyze_spec(spec_path, config=_config(tmp_path))

    assert len(analysis["verification_matrix"]) == 1
    assert analysis["verification_matrix"][0]["name"] == "api-smoke"
    assert analysis["verification_matrix"][0]["blocking_on"] == ["ci", "release"]
    assert verification_matrix_findings(analysis) == []


def test_verification_matrix_requires_cross_repo_profiles(tmp_path: Path) -> None:
    spec_path = _write_spec(
        tmp_path,
        """---
schema_version: 3
name: verification
description: verification
status: approved
owner: platform
targets:
  - ../../api/app/**
  - ../../web/src/**
depends_on: []
required_runtimes: []
required_services: []
required_capabilities: []
stack_projects: []
stack_services: []
stack_capabilities: []
single_slice_reason: ""
multi_domain: false
phases: []
---

# verification

## Slice Breakdown

```yaml
- name: api-main
  targets:
    - ../../api/app/**
  hot_area: api/app
  depends_on: []
- name: web-main
  targets:
    - ../../web/src/**
  hot_area: web/src
  depends_on:
    - api-main
```
""",
    )

    analysis = analyze_spec(spec_path, config=_config(tmp_path))
    findings = verification_matrix_findings(analysis)

    assert any("Verification Matrix" in item for item in findings)
