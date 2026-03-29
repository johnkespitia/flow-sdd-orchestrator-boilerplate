from __future__ import annotations

import json
from pathlib import Path

import pytest

import flowctl.ci as ci
from flowctl.ci import (
    command_ci_integration,
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


def test_t07_json_contract_exposes_ci_clean_traceability(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setenv(
        "FLOW_CI_SERVICE_OVERRIDES",
        json.dumps({"workspace": {"smoke_attempts": 3, "health_timeout_seconds": 60}}),
    )
    monkeypatch.setattr(ci.shutil, "which", lambda _name: "/usr/bin/docker")

    def detect_compose_context() -> dict[str, object]:
        return {"active": True}

    def ensure_devcontainer_env() -> int:
        return 0

    def capture_compose(cmd):  # noqa: ANN001
        if cmd[:2] == ["ps", "--format"]:
            return {"returncode": 0, "stdout": json.dumps([{"Service": "workspace", "Health": "healthy"}]), "output_tail": ""}
        if cmd == ["config", "--services"]:
            return {"returncode": 0, "stdout": "workspace\n", "output_tail": ""}
        return {"returncode": 0, "stdout": "", "output_tail": ""}

    def run_compose(_args):  # noqa: ANN001
        return 0

    def implementation_repos() -> list[str]:
        return []

    def repo_config(_repo):  # noqa: ANN001
        return {}

    def repo_compose_service(_repo):  # noqa: ANN001
        return "workspace"

    def compose_exec_args(service_name, interactive=False, workdir=None):  # noqa: ANN001
        return ["exec", service_name]

    rc = command_ci_integration(
        type("Args", (), {"profile": "smoke:ci-clean", "auto_up": False, "build": False, "bootstrap_runtime": True, "preflight_relaxed": False, "json": True})(),
        require_dirs=lambda: None,
        ensure_devcontainer_env=ensure_devcontainer_env,
        capture_compose=capture_compose,
        detect_compose_context=detect_compose_context,
        run_compose=run_compose,
        implementation_repos=implementation_repos,
        repo_config=repo_config,
        repo_compose_service=repo_compose_service,
        compose_exec_args=compose_exec_args,
        workspace_service="workspace",
        rel=lambda p: str(p),
        format_findings=lambda items: [f"- {item}" for item in items] if items else ["- Sin hallazgos."],
        slugify=lambda value: str(value).replace("/", "-"),
        utc_now=lambda: "2026-01-01T00:00:00+00:00",
        ci_report_root=tmp_path,
        json_dumps=lambda obj: json.dumps(obj),
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["contract"]["ci_clean_profile"] is True
    assert payload["contract"]["strict_preflight"] is True
    assert payload["contract"]["preflight_relaxed"] is False
    assert payload["contract"]["bootstrap_runtime"] is True
    assert payload["contract"]["service_overrides_keys"] == ["workspace"]
