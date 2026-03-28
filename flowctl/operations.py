from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


def _utcparse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # All engine timestamps are UTC ISO8601 with offset.
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def _seconds_between(start: str | None, end: str | None) -> float | None:
    a = _utcparse(start)
    b = _utcparse(end)
    if not a or not b:
        return None
    return max(0.0, (b - a).total_seconds())


def collect_workflow_metrics(*, root: Path, utc_now: Callable[[], str]) -> dict[str, object]:
    flow_root = root / ".flow"
    state_root = flow_root / "state"
    reports_root = flow_root / "reports"
    workflows_root = reports_root / "workflows"

    throughput = 0
    failures = 0
    total_runs = 0
    retries = 0
    stage_latency: dict[str, dict[str, float | int]] = {}
    dlq_size = 0

    # Aggregate metrics from workflow-run reports.
    for path in sorted(workflows_root.glob("*-workflow-run.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        total_runs += 1
        status = str(payload.get("status", "")).strip()
        if status == "completed":
            throughput += 1
        else:
            failures += 1

        for stage in payload.get("stages", []) or []:
            if not isinstance(stage, dict):
                continue
            stage_name = str(stage.get("stage_name", "")).strip()
            if not stage_name:
                continue
            attempt = int(stage.get("attempt", 0) or 0)
            if attempt > 1:
                retries += attempt - 1
            bucket = stage_latency.setdefault(stage_name, {"count": 0, "total_seconds": 0.0})
            delta = _seconds_between(str(stage.get("started_at") or ""), str(stage.get("finished_at") or ""))
            if delta is not None:
                bucket["count"] = int(bucket.get("count", 0) or 0) + 1
                bucket["total_seconds"] = float(bucket.get("total_seconds", 0.0) or 0.0) + float(delta)

        # Workflow-level DLQ (from retry engine).
        for item in payload.get("workflow_dlq", []) or []:
            if isinstance(item, dict):
                dlq_size += 1

    # Aggregate DLQ size from scheduler reports (slice-level).
    for path in sorted(workflows_root.glob("*-scheduler.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        for item in payload.get("dlq", []) or []:
            if isinstance(item, dict):
                dlq_size += 1

    failure_rate = (failures / total_runs) if total_runs else 0.0
    latency_series = []
    for stage_name, bucket in sorted(stage_latency.items()):
        count = int(bucket.get("count", 0) or 0)
        total_sec = float(bucket.get("total_seconds", 0.0) or 0.0)
        avg_sec = (total_sec / count) if count else 0.0
        latency_series.append(
            {
                "stage": stage_name,
                "avg_seconds": avg_sec,
                "samples": count,
            }
        )

    return {
        "generated_at": utc_now(),
        "throughput": throughput,
        "failure_rate": failure_rate,
        "stage_latency": latency_series,
        "retries": retries,
        "dlq_size": dlq_size,
    }


def collect_runs_dashboard(*, root: Path, utc_now: Callable[[], str]) -> dict[str, object]:
    flow_root = root / ".flow"
    state_root = flow_root / "state"
    reports_root = flow_root / "reports"
    workflows_root = reports_root / "workflows"

    runs: list[dict[str, object]] = []
    for state_path in sorted(state_root.glob("*.json")):
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(state, dict):
            continue
        slug = state_path.stem
        engine = state.get("workflow_engine") or {}
        if not isinstance(engine, dict):
            continue
        stages = engine.get("stages") or {}
        if not isinstance(stages, dict):
            stages = {}
        locks = []
        # Derive dashboard entry.
        stage_records = []
        for name, record in stages.items():
            if not isinstance(record, dict):
                continue
            stage_records.append(
                {
                    "stage": str(name),
                    "status": str(record.get("status", "")),
                    "attempt": int(record.get("attempt", 0) or 0),
                    "failure_reason": record.get("failure_reason"),
                }
            )
        run_entry = {
            "feature": slug,
            "engine_status": str(engine.get("status", "")),
            "updated_at": engine.get("updated_at"),
            "paused_at_stage": engine.get("paused_at_stage"),
            "stages": stage_records,
        }
        runs.append(run_entry)

    return {
        "generated_at": utc_now(),
        "runs": runs,
    }


def evaluate_sla_alerts(
    *,
    root: Path,
    utc_now: Callable[[], str],
    thresholds: dict[str, float] | None = None,
) -> dict[str, object]:
    """
    Evalua SLAs por etapa usando latencias agregadas.
    `thresholds` es un mapa opcional stage->segundos; si falta una etapa usa 0 (sin SLA).
    """
    metrics = collect_workflow_metrics(root=root, utc_now=utc_now)
    thresholds = thresholds or {}
    alerts: list[dict[str, object]] = []
    now = utc_now()

    for item in metrics.get("stage_latency", []) or []:
        if not isinstance(item, dict):
            continue
        stage = str(item.get("stage", "")).strip()
        if not stage:
            continue
        avg_seconds = float(item.get("avg_seconds", 0.0) or 0.0)
        threshold = float(thresholds.get(stage, 0.0) or 0.0)
        if threshold <= 0.0:
            continue
        if avg_seconds <= threshold:
            continue
        severity = "warning"
        ratio = avg_seconds / threshold if threshold else 0.0
        if ratio >= 2.0:
            severity = "critical"
        alerts.append(
            {
                "feature": "*",
                "stage": stage,
                "observed_latency": avg_seconds,
                "threshold": threshold,
                "severity": severity,
                "timestamp": now,
                "status": "open",
            }
        )

    return {
        "generated_at": now,
        "alerts": alerts,
    }


def collect_gateway_sqlite_task_metrics(*, db_path: Path) -> dict[str, object]:
    """T14: métricas agregadas leyendo la DB SQLite del gateway (sin importar gateway)."""
    import sqlite3

    if not db_path.is_file():
        return {"available": False, "reason": "database_missing"}
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT source, intent, status, exit_code, created_at, finished_at
            FROM tasks
            ORDER BY created_at DESC
            LIMIT 8000
            """
        ).fetchall()
    finally:
        conn.close()
    buckets: dict[str, dict[str, object]] = {}
    for row in rows:
        src = str(row["source"])
        intent = str(row["intent"])
        key = f"{src}|{intent}"
        b = buckets.setdefault(
            key,
            {"source": src, "intent": intent, "count": 0, "failures": 0, "latencies": []},
        )
        b["count"] = int(b["count"]) + 1  # type: ignore[arg-type]
        st = str(row["status"])
        ec = row["exit_code"]
        if st.startswith("failed") or (ec is not None and int(ec) != 0):
            b["failures"] = int(b["failures"]) + 1  # type: ignore[arg-type]
        fin = row["finished_at"]
        cre = row["created_at"]
        if fin and cre:
            try:
                a = _utcparse(str(cre))
                b_ = _utcparse(str(fin))
                if a and b_:
                    b["latencies"].append(max(0.0, (b_ - a).total_seconds()))  # type: ignore[index]
            except Exception:
                pass
    series: list[dict[str, object]] = []
    for b in buckets.values():
        lat = b["latencies"]  # type: ignore[assignment]
        p95 = 0.0
        if lat:
            s = sorted(lat)
            p95 = s[min(len(s) - 1, int(0.95 * (len(s) - 1)))]
        avg = sum(lat) / len(lat) if lat else 0.0  # type: ignore[arg-type]
        fail_rate = (b["failures"] / b["count"]) if b["count"] else 0.0  # type: ignore[operator]
        series.append(
            {
                "source": b["source"],
                "intent": b["intent"],
                "samples": b["count"],
                "failure_rate": round(float(fail_rate), 4),
                "avg_latency_seconds": round(float(avg), 3),
                "p95_latency_seconds": round(float(p95), 3),
            }
        )
    return {
        "available": True,
        "by_intent_provider": sorted(series, key=lambda x: (str(x["source"]), str(x["intent"]))),
    }


def evaluate_gateway_task_processing_sla(
    *,
    db_path: Path,
    utc_now: Callable[[], str],
    p95_latency_threshold_seconds: float = 3600.0,
    failure_rate_threshold: float = 0.25,
) -> dict[str, object]:
    """T22: alertas simples sobre colas gateway (latencia p95 y tasa de fallo)."""
    metrics = collect_gateway_sqlite_task_metrics(db_path=db_path)
    if not metrics.get("available"):
        return {"generated_at": utc_now(), "alerts": [], "reason": "no_gateway_db"}
    alerts: list[dict[str, object]] = []
    now = utc_now()
    for item in metrics.get("by_intent_provider", []) or []:
        if not isinstance(item, dict):
            continue
        p95 = float(item.get("p95_latency_seconds", 0.0) or 0.0)
        fr = float(item.get("failure_rate", 0.0) or 0.0)
        key = f"{item.get('source')}|{item.get('intent')}"
        if p95 > p95_latency_threshold_seconds:
            alerts.append(
                {
                    "kind": "gateway_latency",
                    "key": key,
                    "p95_latency_seconds": p95,
                    "threshold": p95_latency_threshold_seconds,
                    "severity": "critical" if p95 > p95_latency_threshold_seconds * 2 else "warning",
                    "timestamp": now,
                }
            )
        if fr > failure_rate_threshold:
            alerts.append(
                {
                    "kind": "gateway_failure_rate",
                    "key": key,
                    "failure_rate": fr,
                    "threshold": failure_rate_threshold,
                    "severity": "critical" if fr > 0.5 else "warning",
                    "timestamp": now,
                }
            )
    return {"generated_at": now, "alerts": alerts, "metrics": metrics}


def append_decision(
    *,
    root: Path,
    actor_type: str,
    actor: str,
    decision: str,
    context: str,
    impact_or_risk: str,
    utc_now: Callable[[], str],
) -> dict[str, object]:
    flow_root = root / ".flow"
    reports_root = flow_root / "reports"
    operations_root = reports_root / "operations"
    operations_root.mkdir(parents=True, exist_ok=True)
    decisions_path = operations_root / "decisions.jsonl"
    entry = {
        "actor_type": actor_type,
        "actor": actor,
        "decision": decision,
        "context": context,
        "impact_or_risk": impact_or_risk,
        "timestamp": utc_now(),
    }
    with decisions_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=True) + "\n")
    return entry


def read_decisions(*, root: Path, max_items: int = 100) -> list[dict[str, object]]:
    flow_root = root / ".flow"
    decisions_path = flow_root / "reports" / "operations" / "decisions.jsonl"
    if not decisions_path.exists():
        return []
    items: list[dict[str, object]] = []
    with decisions_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue
            if isinstance(payload, dict):
                items.append(payload)
    return items[-max_items:]

