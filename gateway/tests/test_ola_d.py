"""Ola D (T14–T25): métricas, UI ops, transforms, plantillas, lint, flow_command, idempotencia."""
from __future__ import annotations

import os
import json
import sqlite3
import subprocess
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gateway.app.flow_command import build_flow_command
from gateway.app.gateway_config import load_gateway_block
from gateway.app.intake_idempotency import semantic_intake_key
from gateway.app.spec_quality import lint_inbound_spec_payload
from gateway.app.store import TaskStore
from gateway.app.transforms import apply_source_transforms


def test_t14_aggregate_intent_provider_metrics(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    store = TaskStore(db)
    store.initialize()
    store.enqueue(
        source="github",
        intent="workflow.intake",
        payload={"slug": "a", "title": "T", "repos": ["root"]},
        command=["x"],
        response_target=None,
    )
    rows = store.recent_tasks(limit=5)
    assert rows
    tid = rows[0]["task_id"]
    with store._connect() as c:  # type: ignore[attr-defined]
        c.execute(
            "UPDATE tasks SET status=?, exit_code=?, finished_at=? WHERE task_id=?",
            ("succeeded", 0, "2026-01-01T00:00:10+00:00", tid),
        )
        c.commit()
    m = store.aggregate_intent_provider_metrics(limit_rows=100)
    assert "by_intent_provider" in m
    assert m["by_intent_provider"]


def test_t15_ops_monitor_html(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from gateway.app import config as gateway_config
    from gateway.app.main import app

    db = tmp_path / "g.db"

    def _load() -> gateway_config.Settings:
        return gateway_config.Settings(
            workspace_root=tmp_path,
            database_path=db,
            flow_bin="python3",
            flow_entrypoint="./flow",
            gateway_api_token=None,
            slack_signing_secret=None,
            github_webhook_secret=None,
            jira_webhook_token=None,
            default_feedback_provider=None,
            worker_poll_interval=0.05,
        )

    monkeypatch.setattr(gateway_config, "load_settings", _load)
    import gateway.app.main as gm

    monkeypatch.setattr(gm, "load_settings", _load)
    with TestClient(app) as client:
        r = client.get("/v1/ops/monitor")
        assert r.status_code == 200
        assert "task monitor" in r.text.lower()


def test_t16_transforms_github_strip_prefix(tmp_path: Path) -> None:
    (tmp_path / "workspace.config.json").write_text(json.dumps({"gateway": {"transforms": {"github": [{"op": "strip_prefix", "field": "title", "prefix": "[x] "}]}}}), encoding="utf-8")
    out = apply_source_transforms("github", {"title": "[x] Hello", "slug": "s"}, tmp_path)
    assert out["title"] == "Hello"


def test_t17_feedback_template_from_config(tmp_path: Path) -> None:
    (tmp_path / "workspace.config.json").write_text(
        json.dumps(
            {
                "gateway": {
                    "feedback_templates": {"workflow.intake": "ID={task_id} I={intent}\n{body}"}
                }
            }
        ),
        encoding="utf-8",
    )
    from gateway.app.config import Settings
    from gateway.app.feedback import _feedback_message

    s = Settings(
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
    msg = _feedback_message(
        {"task_id": "abc", "intent": "workflow.intake", "status": "queued", "stdout": "", "stderr": "", "exit_code": None},
        settings=s,
    )
    assert "abc" in msg and "workflow.intake" in msg


def test_t18_lint_inbound_detects_issues() -> None:
    issues = lint_inbound_spec_payload({"title": "x\tbad", "description": "recieve"})
    assert any("tab" in i for i in issues)
    assert any("recieve" in i for i in issues)


def test_t19_build_flow_command_module() -> None:
    root = Path(__file__).resolve().parents[2]
    cmd = build_flow_command("status.get", {}, workspace_root=root)
    assert cmd == ["status", "--json"]


def test_t20_enqueue_idempotent_under_concurrency(tmp_path: Path) -> None:
    db = tmp_path / "c.db"
    store = TaskStore(db)
    store.initialize()
    payload = {"slug": "dup", "title": "Dup", "repos": ["root"]}
    results: list[str] = []

    def run() -> None:
        t = store.enqueue(
            source="api",
            intent="workflow.intake",
            payload=payload,
            command=["flow"],
            response_target=None,
        )
        results.append(t["task_id"])

    threads = [threading.Thread(target=run) for _ in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert len(set(results)) == 1


def test_t24_playbook_exists() -> None:
    root = Path(__file__).resolve().parents[2]
    p = root / "docs" / "playbook-workflow-rollback.md"
    text = p.read_text(encoding="utf-8").lower()
    assert p.is_file() and "rollback" in text and "dry-run" in text


def test_t25_onboarding_checklist_exists() -> None:
    root = Path(__file__).resolve().parents[2]
    p = root / "docs" / "onboarding-team-checklist.md"
    text = p.read_text(encoding="utf-8")
    assert "[ ]" in text or "- [ ]" in text


def test_program_closure_evidence_matrix_exists() -> None:
    root = Path(__file__).resolve().parents[2]
    p = root / "docs" / "program-closure-evidence-matrix.md"
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "| Txx | archivo | test/comando | resultado |" in text
    for token in (
        "T22",
        "T23",
        "T24",
        "T25",
        "docs/gateway-sla-incidents.md",
        "docs/flow-reports-retention.md",
        "docs/playbook-workflow-rollback.md",
        "docs/onboarding-team-checklist.md",
        "python3 ./flow ops sla --json",
        "python3 -m pytest -q gateway/tests/test_ola_d.py -k t23",
        "python3 -m pytest -q gateway/tests/test_ola_d.py -k t24",
        "python3 -m pytest -q gateway/tests/test_ola_d.py -k t25",
    ):
        assert token in text


def test_t23_retention_script_syntax(repo_root: Path) -> None:
    script = repo_root / "scripts" / "flow_reports_retention.sh"
    subprocess.run(["bash", "-n", str(script)], check=True)


def test_t23_retention_script_enforces_dry_run_and_confirm(repo_root: Path, tmp_path: Path) -> None:
    script = repo_root / "scripts" / "flow_reports_retention.sh"
    reports_root = tmp_path / ".flow" / "reports" / "ci"
    reports_root.mkdir(parents=True, exist_ok=True)
    old_report = reports_root / "old.json"
    recent_report = reports_root / "recent.json"
    old_report.write_text("old", encoding="utf-8")
    recent_report.write_text("recent", encoding="utf-8")
    old_timestamp = 1_700_000_000
    recent_timestamp = 1_800_000_000
    os.utime(old_report, (old_timestamp, old_timestamp))
    os.utime(recent_report, (recent_timestamp, recent_timestamp))

    dry_run = subprocess.run(
        [
            "bash",
            str(script),
        ],
        cwd=repo_root,
        env={
            **os.environ,
            "FLOW_WORKSPACE_ROOT": str(tmp_path),
            "FLOW_REPORTS_RETENTION_DAYS": "30",
            "FLOW_REPORTS_RETENTION_CONFIRM": "0",
        },
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Dry-run" in dry_run.stdout
    assert old_report.exists()
    assert recent_report.exists()

    apply_run = subprocess.run(
        [
            "bash",
            str(script),
        ],
        cwd=repo_root,
        env={
            **os.environ,
            "FLOW_WORKSPACE_ROOT": str(tmp_path),
            "FLOW_REPORTS_RETENTION_DAYS": "30",
            "FLOW_REPORTS_RETENTION_CONFIRM": "1",
        },
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Limpieza aplicada" in apply_run.stdout
    assert not old_report.exists()
    assert recent_report.exists()


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_semantic_intake_key_stable() -> None:
    a = semantic_intake_key({"slug": "z"})
    b = semantic_intake_key({"slug": "z"})
    assert a == b


def test_load_gateway_block_empty(tmp_path: Path) -> None:
    assert load_gateway_block(tmp_path) == {}
