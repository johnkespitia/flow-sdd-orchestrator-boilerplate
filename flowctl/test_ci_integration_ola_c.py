from __future__ import annotations

import json
from pathlib import Path

import pytest

from flowctl.ci import (
    integration_profile_is_ci_clean,
    load_ci_service_overrides_from_env,
    merge_service_integration_settings,
    resolve_ci_strict_preflight,
)


def test_t07_contract_doc_matches_implementation_keywords() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = root / "docs" / "smoke-ci-clean-contract.md"
    text = doc.read_text(encoding="utf-8")
    assert "smoke:ci-clean" in text
    assert "FAIL" in text and "PASS" in text
    assert "FLOW_CI_SERVICE_OVERRIDES" in text
    assert "preflight-relaxed" in text or "`--preflight-relaxed`" in text


def test_t08_root_ci_enforces_smoke_ci_clean_gate() -> None:
    root = Path(__file__).resolve().parents[1]
    wf = root / ".github" / "workflows" / "root-ci.yml"
    content = wf.read_text(encoding="utf-8")
    assert "smoke:ci-clean" in content
    assert "ci integration" in content


def test_t09_bootstrap_flag_documented_in_flow_help() -> None:
    import subprocess

    r = subprocess.run(
        ["python3", str(Path(__file__).resolve().parents[1] / "flow"), "ci", "integration", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    assert "--bootstrap-runtime" in r.stdout


def test_t10_strict_preflight_default_for_ci_clean() -> None:
    assert resolve_ci_strict_preflight("smoke:ci-clean", preflight_relaxed=False) is True
    assert resolve_ci_strict_preflight("smoke:ci-clean", preflight_relaxed=True) is False
    assert resolve_ci_strict_preflight("smoke", preflight_relaxed=False) is False


def test_t11_service_overrides_merge_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FLOW_CI_SERVICE_OVERRIDES", raising=False)
    assert load_ci_service_overrides_from_env() == {}
    monkeypatch.setenv(
        "FLOW_CI_SERVICE_OVERRIDES",
        json.dumps({"workspace": {"smoke_attempts": 2, "smoke_backoff_seconds": 0.5}}),
    )
    loaded = load_ci_service_overrides_from_env()
    assert "workspace" in loaded
    merged = merge_service_integration_settings(
        "workspace",
        loaded,
        default_attempts=4,
        default_backoff=2.0,
        default_health_timeout=30,
        default_health_poll=2,
    )
    assert merged["smoke_attempts"] == 2
    assert merged["smoke_backoff_seconds"] == 0.5
    merged_default = merge_service_integration_settings(
        "db",
        loaded,
        default_attempts=4,
        default_backoff=2.0,
        default_health_timeout=30,
        default_health_poll=2,
    )
    assert merged_default["smoke_attempts"] == 4


def test_integration_profile_is_ci_clean_aliases() -> None:
    assert integration_profile_is_ci_clean("smoke:ci-clean") is True
    assert integration_profile_is_ci_clean("SMOKE:CI-CLEAN") is True
    assert integration_profile_is_ci_clean("smoke") is False
