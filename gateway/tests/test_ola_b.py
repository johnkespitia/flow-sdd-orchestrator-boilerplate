"""Ola B (T05, T06, T12, T13): deploy central, feedback retry, pull_request, Jira custom AC."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gateway.app.config import Settings
from gateway.app.feedback import (
    FeedbackRetryConfig,
    _merge_retry_config,
    _resolve_retry_config,
    send_feedback,
)
from gateway.app.intents import intent_from_github, intent_from_jira, load_jira_acceptance_criteria_field_id
from gateway.app.webhook_validation import validate_github_payload


# --- T05 ---


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_t05_runbook_and_scripts_exist_and_smoke_syntax(repo_root: Path) -> None:
    runbook = repo_root / "docs/gateway-central-deployment-runbook.md"
    smoke = repo_root / "scripts/gateway_central_smoke.sh"
    start = repo_root / "scripts/gateway_central_start.sh"
    assert runbook.is_file()
    assert smoke.is_file() and start.is_file()
    subprocess.run(["bash", "-n", str(smoke)], check=True)
    subprocess.run(["bash", "-n", str(start)], check=True)


# --- T06 ---


def _write_stub_feedback_script(tmp: Path) -> None:
    ep = tmp / "scripts/providers/feedback/local_log.sh"
    ep.parent.mkdir(parents=True, exist_ok=True)
    ep.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")


def _minimal_settings(tmp: Path) -> Settings:
    _write_stub_feedback_script(tmp)
    (tmp / "workspace.providers.json").write_text(
        json.dumps(
            {
                "feedback": {
                    "default_provider": "local-log",
                    "retry_policy": {
                        "max_attempts": 5,
                        "initial_delay_s": 0.01,
                        "max_delay_s": 0.1,
                        "backoff_multiplier": 2.0,
                    },
                    "providers": {
                        "local-log": {
                            "enabled": True,
                            "entrypoint": "scripts/providers/feedback/local_log.sh",
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    return Settings(
        workspace_root=tmp,
        database_path=tmp / "db.sqlite",
        flow_bin="python3",
        flow_entrypoint="./flow",
        gateway_api_token=None,
        slack_signing_secret=None,
        github_webhook_secret=None,
        jira_webhook_token=None,
        default_feedback_provider=None,
        worker_poll_interval=0.1,
    )


def test_t06_transient_retries_then_success(tmp_path: Path) -> None:
    settings = _minimal_settings(tmp_path)
    task = {
        "task_id": "t1",
        "intent": "workflow.intake",
        "status": "succeeded",
        "source": "worker",
        "response_target": {"provider": "local-log", "kind": "none"},
        "stdout": "",
        "stderr": "",
        "exit_code": 0,
    }
    calls: list[int] = []

    def fake_run(*_a: object, **_k: object) -> MagicMock:
        calls.append(1)
        m = MagicMock()
        if len(calls) < 3:
            m.returncode = 1
            m.stderr = "network"
            m.stdout = ""
        else:
            m.returncode = 0
            m.stderr = ""
            m.stdout = "ok"
        return m

    with patch("gateway.app.feedback._run_feedback_bash", side_effect=fake_run):
        with patch("gateway.app.feedback._sleep"):
            out = send_feedback(settings, task)
    assert out is not None
    assert out["return_code"] == 0
    assert out["attempts_used"] == 3
    assert len(calls) == 3


def test_t06_permanent_exit_code_no_retry(tmp_path: Path) -> None:
    settings = _minimal_settings(tmp_path)
    task = {
        "task_id": "t1",
        "intent": "workflow.intake",
        "status": "succeeded",
        "source": "worker",
        "response_target": {"provider": "local-log"},
        "stdout": "",
        "stderr": "",
        "exit_code": 0,
    }

    def fake_run(*_a: object, **_k: object) -> MagicMock:
        m = MagicMock()
        m.returncode = 2
        m.stderr = "bad config"
        m.stdout = ""
        return m

    with patch("gateway.app.feedback._run_feedback_bash", side_effect=fake_run):
        with patch("gateway.app.feedback._sleep") as mock_sleep:
            out = send_feedback(settings, task)
    assert out is not None
    assert out["return_code"] == 2
    assert out["attempts_used"] == 1
    mock_sleep.assert_not_called()


def test_t06_permanent_stderr_prefix_no_retry(tmp_path: Path) -> None:
    settings = _minimal_settings(tmp_path)
    task = {
        "task_id": "t1",
        "intent": "workflow.intake",
        "status": "succeeded",
        "source": "worker",
        "response_target": {"provider": "local-log"},
        "stdout": "",
        "stderr": "",
        "exit_code": 0,
    }

    def fake_run(*_a: object, **_k: object) -> MagicMock:
        m = MagicMock()
        m.returncode = 1
        m.stderr = "PERMANENT: token revoked"
        m.stdout = ""
        return m

    with patch("gateway.app.feedback._run_feedback_bash", side_effect=fake_run):
        with patch("gateway.app.feedback._sleep") as mock_sleep:
            out = send_feedback(settings, task)
    assert out is not None
    assert out["attempts_used"] == 1
    mock_sleep.assert_not_called()


def test_t06_transient_exhausts_max_attempts(tmp_path: Path) -> None:
    _write_stub_feedback_script(tmp_path)
    manifest = {
        "feedback": {
            "default_provider": "local-log",
            "retry_policy": {"max_attempts": 3, "initial_delay_s": 0.01, "max_delay_s": 0.05, "backoff_multiplier": 2.0},
            "providers": {
                "local-log": {
                    "enabled": True,
                    "entrypoint": "scripts/providers/feedback/local_log.sh",
                }
            },
        }
    }
    (tmp_path / "workspace.providers.json").write_text(json.dumps(manifest), encoding="utf-8")
    settings = Settings(
        workspace_root=tmp_path,
        database_path=tmp_path / "db.sqlite",
        flow_bin="python3",
        flow_entrypoint="./flow",
        gateway_api_token=None,
        slack_signing_secret=None,
        github_webhook_secret=None,
        jira_webhook_token=None,
        default_feedback_provider=None,
        worker_poll_interval=0.1,
    )
    task = {
        "task_id": "t1",
        "intent": "x",
        "status": "succeeded",
        "source": "worker",
        "response_target": {"provider": "local-log"},
        "stdout": "",
        "stderr": "",
        "exit_code": 0,
    }

    def fake_run(*_a: object, **_k: object) -> MagicMock:
        m = MagicMock()
        m.returncode = 1
        m.stderr = "fail"
        m.stdout = ""
        return m

    with patch("gateway.app.feedback._run_feedback_bash", side_effect=fake_run):
        with patch("gateway.app.feedback._sleep") as mock_sleep:
            out = send_feedback(settings, task)
    assert out is not None
    assert out["attempts_used"] == 3
    assert out["return_code"] == 1
    assert mock_sleep.call_count == 2


def test_t06_backoff_intervals(mock_sleep: MagicMock, tmp_path: Path) -> None:
    settings = _minimal_settings(tmp_path)
    task = {
        "task_id": "t1",
        "intent": "x",
        "status": "ok",
        "source": "worker",
        "response_target": {"provider": "local-log"},
        "stdout": "",
        "stderr": "",
        "exit_code": 0,
    }

    def fake_run(*_a: object, **_k: object) -> MagicMock:
        m = MagicMock()
        m.returncode = 1
        m.stderr = "x"
        m.stdout = ""
        return m

    with patch("gateway.app.feedback._run_feedback_bash", side_effect=fake_run):
        send_feedback(settings, task)
    delays = [c[0][0] for c in mock_sleep.call_args_list]
    assert len(delays) >= 2
    assert delays[0] <= delays[1]


@pytest.fixture
def mock_sleep() -> MagicMock:
    with patch("gateway.app.feedback._sleep") as m:
        yield m


def test_t06_merge_retry_config_partial_overlay() -> None:
    base = FeedbackRetryConfig(max_attempts=4, initial_delay_s=0.5, max_delay_s=8.0, backoff_multiplier=2.0)
    merged = _merge_retry_config(base, {"max_attempts": 2})
    assert merged.max_attempts == 2
    assert merged.initial_delay_s == 0.5


def test_t06_resolve_retry_provider_override(tmp_path: Path) -> None:
    _write_stub_feedback_script(tmp_path)
    (tmp_path / "workspace.providers.json").write_text(
        json.dumps(
            {
                "feedback": {
                    "default_provider": "local-log",
                    "retry_policy": {"max_attempts": 10},
                    "providers": {
                        "local-log": {
                            "enabled": True,
                            "entrypoint": "scripts/providers/feedback/local_log.sh",
                            "retry_policy": {"max_attempts": 2},
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    settings = Settings(
        workspace_root=tmp_path,
        database_path=tmp_path / "x.db",
        flow_bin="python3",
        flow_entrypoint="./flow",
        gateway_api_token=None,
        slack_signing_secret=None,
        github_webhook_secret=None,
        jira_webhook_token=None,
        default_feedback_provider=None,
        worker_poll_interval=0.1,
    )
    import gateway.app.feedback as fb

    section = fb._load_feedback_section(settings)
    prov = section["providers"]["local-log"]
    cfg = _resolve_retry_config(settings, section, prov)
    assert cfg.max_attempts == 2


# --- T12 ---


def test_t12_pull_request_opened_maps_to_intake() -> None:
    payload = {
        "action": "opened",
        "repository": {"full_name": "org/repo"},
        "pull_request": {
            "title": "Feature PR",
            "body": "desc",
            "number": 7,
            "labels": [{"name": "flow-spec"}, {"name": "flow-repo:root"}],
            "comments_url": "https://api.github.com/repos/org/repo/issues/7/comments",
        },
    }
    ok, code, _ = validate_github_payload("pull_request", payload)
    assert ok and code == ""
    req = intent_from_github("pull_request", payload)
    assert req is not None
    assert req.intent == "workflow.intake"
    assert req.payload.get("slug")
    assert req.payload.get("title") == "Feature PR"


def test_t12_pull_request_edited() -> None:
    payload = {
        "action": "edited",
        "repository": {"full_name": "o/r"},
        "pull_request": {
            "title": "T",
            "body": "b",
            "number": 1,
            "labels": [{"name": "flow-spec"}],
            "comments_url": "https://x",
        },
    }
    assert validate_github_payload("pull_request", payload)[0]
    req = intent_from_github("pull_request", payload)
    assert req is not None and req.intent == "workflow.intake"


def test_t12_pull_request_labeled_flow_spec() -> None:
    payload = {
        "action": "labeled",
        "repository": {"full_name": "o/r"},
        "label": {"name": "flow-spec"},
        "pull_request": {
            "title": "T",
            "body": "",
            "number": 2,
            "labels": [{"name": "flow-spec"}],
            "comments_url": "https://x",
        },
    }
    assert validate_github_payload("pull_request", payload)[0]
    req = intent_from_github("pull_request", payload)
    assert req is not None


def test_t12_pull_request_labeled_other_ignored() -> None:
    payload = {
        "action": "labeled",
        "repository": {"full_name": "o/r"},
        "label": {"name": "bug"},
        "pull_request": {
            "title": "T",
            "body": "",
            "number": 2,
            "labels": [],
            "comments_url": "https://x",
        },
    }
    assert intent_from_github("pull_request", payload) is None


# --- T13 ---


def test_t13_load_ac_field_from_manifest(tmp_path: Path) -> None:
    (tmp_path / "workspace.providers.json").write_text(
        json.dumps({"gateway": {"jira": {"acceptance_criteria_field": "customfield_10001"}}}),
        encoding="utf-8",
    )
    assert load_jira_acceptance_criteria_field_id(tmp_path) == "customfield_10001"


def test_t13_jira_intake_merges_custom_field(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FLOW_WORKSPACE_ROOT", str(tmp_path))
    (tmp_path / "workspace.providers.json").write_text(
        json.dumps(
            {
                "gateway": {"jira": {"acceptance_criteria_field": "customfield_999"}},
                "feedback": {
                    "default_provider": "local-log",
                    "providers": {
                        "local-log": {"enabled": True, "entrypoint": "scripts/providers/feedback/local_log.sh"}
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    payload = {
        "issue": {
            "key": "K-1",
            "fields": {
                "summary": "Story",
                "labels": ["flow-repo:root"],
                "customfield_999": "- One\n- Two",
            }
        }
    }
    req = intent_from_jira(payload)
    assert req is not None
    ac = req.payload.get("acceptance_criteria")
    assert isinstance(ac, list)
    assert "One" in ac and "Two" in ac


def test_t13_env_overrides_manifest(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FLOW_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("SOFTOS_JIRA_ACCEPTANCE_FIELD", "customfield_env")
    (tmp_path / "workspace.providers.json").write_text(
        json.dumps({"gateway": {"jira": {"acceptance_criteria_field": "customfield_999"}}}),
        encoding="utf-8",
    )
    payload = {
        "issue": {
            "key": "K-2",
            "fields": {
                "summary": "S",
                "labels": ["flow-repo:root"],
                "customfield_env": "from env",
                "customfield_999": "from manifest",
            },
        }
    }
    req = intent_from_jira(payload)
    assert req is not None
    ac = req.payload.get("acceptance_criteria") or []
    assert "from env" in ac
    assert "from manifest" not in ac


def test_t13_fallback_without_custom_field(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FLOW_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.delenv("SOFTOS_JIRA_ACCEPTANCE_FIELD", raising=False)
    (tmp_path / "workspace.providers.json").write_text(json.dumps({}), encoding="utf-8")
    payload = {
        "issue": {
            "key": "K-3",
            "fields": {
                "summary": "S",
                "labels": ["flow-repo:root"],
                "acceptance_criteria": ["alpha", "beta"],
            },
        }
    }
    req = intent_from_jira(payload)
    assert req is not None
    assert set(req.payload.get("acceptance_criteria") or []) == {"alpha", "beta"}


def test_t13_normalize_list_and_string_in_custom_field(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FLOW_WORKSPACE_ROOT", str(tmp_path))
    (tmp_path / "workspace.providers.json").write_text(
        json.dumps({"gateway": {"jira": {"acceptance_criteria_field_id": "customfield_x"}}}),
        encoding="utf-8",
    )
    payload = {
        "issue": {
            "key": "K-4",
            "fields": {
                "summary": "S",
                "labels": ["flow-repo:root"],
                "customfield_x": ["a", "b"],
            },
        }
    }
    req = intent_from_jira(payload)
    assert req is not None
    assert req.payload.get("acceptance_criteria") == ["a", "b"]
