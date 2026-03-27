from __future__ import annotations

import json
import tempfile
from pathlib import Path

import sys

import pytest
from fastapi.testclient import TestClient


@pytest.mark.skipif(sys.version_info < (3, 10), reason="Gateway models use modern typing that requires Python 3.10+ for Pydantic 2.")
def test_metrics_endpoint_returns_required_fields(monkeypatch) -> None:  # type: ignore[override]
    # Reconfigura workspace_root temporalmente para que el endpoint lea métricas de un workspace aislado.
    from gateway.app import config as gateway_config
    from gateway.app.main import app

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # Crear layout mínimo esperado para collect_workflow_metrics.
        reports = root / ".flow" / "reports" / "workflows"
        reports.mkdir(parents=True, exist_ok=True)
        payload = {
            "status": "completed",
            "stages": [],
            "workflow_dlq": [],
        }
        (reports / "demo-workflow-run.json").write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")

        def _load_settings() -> gateway_config.Settings:
            return gateway_config.Settings(
                workspace_root=root,
                database_path=root / "tasks.db",
                flow_bin="python3",
                flow_entrypoint="./flow",
                gateway_api_token=None,
                slack_signing_secret=None,
                github_webhook_secret=None,
                jira_webhook_token=None,
                default_feedback_provider=None,
                worker_poll_interval=0.01,
            )

        monkeypatch.setattr(gateway_config, "load_settings", _load_settings)
        # `gateway.app.main` ya importó `load_settings`, así que también hay que patchar el símbolo local.
        import gateway.app.main as gateway_main

        monkeypatch.setattr(gateway_main, "load_settings", _load_settings)

        # Usar context manager para disparar lifespan y setear app.state.settings/store/worker.
        with TestClient(app) as client:
            response = client.get("/metrics")
        assert response.status_code == 200
        body = response.json()
        assert "throughput" in body
        assert "failure_rate" in body
        assert "stage_latency" in body
        assert "retries" in body
        assert "dlq_size" in body


def test_collect_workflow_metrics_directly() -> None:
    # Test alternativo que corre en Python 3.9+ y verifica el shape del payload
    # sin depender del stack completo de FastAPI/Pydantic.
    from flowctl.operations import collect_workflow_metrics

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        reports = root / ".flow" / "reports" / "workflows"
        reports.mkdir(parents=True, exist_ok=True)
        payload = {
            "status": "completed",
            "stages": [],
            "workflow_dlq": [],
        }
        (reports / "demo-workflow-run.json").write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")

        metrics = collect_workflow_metrics(root=root, utc_now=lambda: "2026-01-01T00:00:00+00:00")
        assert "throughput" in metrics
        assert "failure_rate" in metrics
        assert "stage_latency" in metrics
        assert "retries" in metrics
        assert "dlq_size" in metrics

