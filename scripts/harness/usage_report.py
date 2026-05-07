#!/usr/bin/env python3
"""Create SoftOS Harness usage/cost checkpoints and closeout summaries.

This helper is intentionally stdlib-only. It does not call provider APIs or
store credentials. It records exact, provider-reconciled, or estimated usage
that the operator/agent provides, and can compute an estimated USD cost when
per-million-token rates are passed on the command line.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VALID_MODES = {"exact", "provider_reconciled", "estimated"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slug(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-") or "usage"


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        raise SystemExit(f"missing file: {path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON in {path}: {exc}") from exc


def load_profile(root: Path, profile_id: str) -> dict[str, Any]:
    path = root / "profiles" / profile_id / "profile.json"
    profile = load_json(path)
    usage = profile.get("usage_telemetry")
    if not isinstance(usage, dict) or usage.get("enabled") is not True:
        raise SystemExit(f"profile {profile_id} does not enable usage_telemetry")
    return profile


def default_report_path(root: Path, profile: dict[str, Any], ticket: str) -> Path:
    template = (
        profile.get("usage_telemetry", {})
        .get("evidence", {})
        .get("default_json_path_template", "docs/evidence/{ticket}-usage-and-cost.json")
    )
    return root / template.format(ticket=slug(ticket))


def money(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"${value:.6f}"


def compute_cost(args: argparse.Namespace) -> float | None:
    explicit = getattr(args, "cost_usd", None)
    if explicit is not None:
        return explicit
    rate_fields = [
        args.input_rate_per_mtok,
        args.cached_input_rate_per_mtok,
        args.output_rate_per_mtok,
        args.tool_cost_usd,
    ]
    if all(value is None for value in rate_fields):
        return None
    input_tokens = args.input_tokens or 0
    cached_tokens = args.cached_input_tokens or 0
    uncached_input = max(input_tokens - cached_tokens, 0)
    output_tokens = args.output_tokens or 0
    total = 0.0
    if args.input_rate_per_mtok is not None:
        total += uncached_input * args.input_rate_per_mtok / 1_000_000
    if args.cached_input_rate_per_mtok is not None:
        total += cached_tokens * args.cached_input_rate_per_mtok / 1_000_000
    elif args.input_rate_per_mtok is not None:
        # Conservative fallback when no cached rate is provided.
        total += cached_tokens * args.input_rate_per_mtok / 1_000_000
    if args.output_rate_per_mtok is not None:
        total += output_tokens * args.output_rate_per_mtok / 1_000_000
    if args.tool_cost_usd is not None:
        total += args.tool_cost_usd
    return total


def empty_report(ticket: str, profile_id: str, root: Path) -> dict[str, Any]:
    now = utc_now()
    return {
        "schema_version": "usage-and-cost-report/v1",
        "ticket": ticket,
        "profile_id": profile_id,
        "root": str(root),
        "created_at": now,
        "updated_at": now,
        "checkpoints": [],
        "notes": [
            "Each checkpoint must declare mode: exact, provider_reconciled, or estimated.",
            "Provider-reconciled cost is the financial source of truth when available; provider data may lag.",
        ],
    }


def load_or_create_report(path: Path, ticket: str, profile_id: str, root: Path) -> dict[str, Any]:
    if path.exists():
        return load_json(path)
    return empty_report(ticket=ticket, profile_id=profile_id, root=root)


def add_checkpoint(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    profile = load_profile(root, args.profile)
    path = Path(args.output).resolve() if args.output else default_report_path(root, profile, args.ticket)
    path.parent.mkdir(parents=True, exist_ok=True)
    report = load_or_create_report(path, args.ticket, args.profile, root)

    if args.mode not in VALID_MODES:
        raise SystemExit(f"invalid mode {args.mode!r}; expected one of {sorted(VALID_MODES)}")

    cost = compute_cost(args)
    checkpoint = {
        "timestamp": utc_now(),
        "window": args.window,
        "phase": args.phase,
        "gate": args.gate,
        "agent": args.agent,
        "process": args.process,
        "repo": args.repo,
        "model": args.model,
        "tool": args.tool,
        "mode": args.mode,
        "requests": args.requests or 0,
        "input_tokens": args.input_tokens or 0,
        "cached_input_tokens": args.cached_input_tokens or 0,
        "output_tokens": args.output_tokens or 0,
        "tool_calls": args.tool_calls or 0,
        "tool_sessions": args.tool_sessions or 0,
        "cost_usd": cost,
        "confidence": args.confidence,
        "source": args.source,
        "note": args.note,
    }
    report.setdefault("checkpoints", []).append(checkpoint)
    report["updated_at"] = utc_now()
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(format_checkpoint(checkpoint, path))
    return 0


def totals_by(checkpoints: list[dict[str, Any]], key: str) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for item in checkpoints:
        bucket = str(item.get(key) or "unknown")
        result[bucket]["requests"] += item.get("requests") or 0
        result[bucket]["input_tokens"] += item.get("input_tokens") or 0
        result[bucket]["cached_input_tokens"] += item.get("cached_input_tokens") or 0
        result[bucket]["output_tokens"] += item.get("output_tokens") or 0
        result[bucket]["tool_calls"] += item.get("tool_calls") or 0
        result[bucket]["tool_sessions"] += item.get("tool_sessions") or 0
        if item.get("cost_usd") is not None:
            result[bucket]["cost_usd"] += item.get("cost_usd") or 0
    return result


def total(checkpoints: list[dict[str, Any]], field: str) -> float:
    return sum((item.get(field) or 0) for item in checkpoints)


def total_cost(checkpoints: list[dict[str, Any]]) -> float | None:
    values = [item.get("cost_usd") for item in checkpoints if item.get("cost_usd") is not None]
    if not values:
        return None
    return float(sum(values))


def format_checkpoint(checkpoint: dict[str, Any], path: Path) -> str:
    return "\n".join([
        "Usage update:",
        f"- Report: {path}",
        f"- Window: {checkpoint.get('window') or 'n/a'}",
        f"- Phase/gate: {checkpoint.get('phase') or 'n/a'} / {checkpoint.get('gate') or 'n/a'}",
        f"- Agent/process: {checkpoint.get('agent') or 'n/a'} / {checkpoint.get('process') or 'n/a'}",
        f"- Mode: {checkpoint.get('mode')}",
        f"- Requests: {checkpoint.get('requests', 0)}",
        f"- Input tokens: {checkpoint.get('input_tokens', 0)}",
        f"- Cached input tokens: {checkpoint.get('cached_input_tokens', 0)}",
        f"- Output tokens: {checkpoint.get('output_tokens', 0)}",
        f"- Tool calls/sessions: {checkpoint.get('tool_calls', 0)} / {checkpoint.get('tool_sessions', 0)}",
        f"- Cost: {money(checkpoint.get('cost_usd'))}",
        f"- Confidence: {checkpoint.get('confidence') or 'n/a'}",
        f"- Notes/caveats: {checkpoint.get('note') or 'n/a'}",
    ])


def markdown_summary(report: dict[str, Any]) -> str:
    checkpoints = report.get("checkpoints", [])
    cost = total_cost(checkpoints)
    lines = [
        "# Usage & Cost Report",
        "",
        f"- Ticket: {report.get('ticket')}",
        f"- Profile: {report.get('profile_id')}",
        f"- Updated: {report.get('updated_at')}",
        f"- Checkpoints: {len(checkpoints)}",
        f"- Requests: {int(total(checkpoints, 'requests'))}",
        f"- Input tokens: {int(total(checkpoints, 'input_tokens'))}",
        f"- Cached input tokens: {int(total(checkpoints, 'cached_input_tokens'))}",
        f"- Output tokens: {int(total(checkpoints, 'output_tokens'))}",
        f"- Tool calls: {int(total(checkpoints, 'tool_calls'))}",
        f"- Tool sessions: {int(total(checkpoints, 'tool_sessions'))}",
        f"- Cost: {money(cost)}",
        "",
        "## Breakdown by mode",
        "",
    ]
    for mode, values in sorted(totals_by(checkpoints, "mode").items()):
        lines.append(
            f"- {mode}: requests={int(values['requests'])}, input={int(values['input_tokens'])}, "
            f"cached={int(values['cached_input_tokens'])}, output={int(values['output_tokens'])}, "
            f"cost={money(values.get('cost_usd'))}"
        )
    for key in ["phase", "agent", "model", "tool", "repo"]:
        lines.extend(["", f"## Breakdown by {key}", ""])
        for bucket, values in sorted(totals_by(checkpoints, key).items()):
            lines.append(
                f"- {bucket}: requests={int(values['requests'])}, input={int(values['input_tokens'])}, "
                f"cached={int(values['cached_input_tokens'])}, output={int(values['output_tokens'])}, "
                f"cost={money(values.get('cost_usd'))}"
            )
    lines.extend(["", "## Caveats", ""])
    notes = report.get("notes") or []
    for note in notes:
        lines.append(f"- {note}")
    if any(item.get("mode") == "estimated" for item in checkpoints):
        lines.append("- Some checkpoints are estimated because exact per-turn usage was unavailable locally.")
    if any(item.get("mode") == "provider_reconciled" for item in checkpoints):
        lines.append("- Provider-reconciled values may lag but should be treated as the financial source of truth when available.")
    return "\n".join(lines) + "\n"


def openai_get(base_url: str, path: str, api_key: str, params: dict[str, Any]) -> dict[str, Any]:
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}, doseq=True)
    url = base_url.rstrip("/") + path + (f"?{query}" if query else "")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:  # noqa: S310 - operator-provided API URL/key
            payload = response.read().decode("utf-8")
    except Exception as exc:  # pragma: no cover - network/operator environment
        raise SystemExit(f"provider snapshot request failed for {path}: {exc}") from exc
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"provider snapshot returned invalid JSON for {path}: {exc}") from exc


def parse_provider_totals(payload: dict[str, Any]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            if "input_tokens" in node:
                totals["input_tokens"] += node.get("input_tokens") or 0
            if "input_cached_tokens" in node:
                totals["cached_input_tokens"] += node.get("input_cached_tokens") or 0
            if "cached_input_tokens" in node:
                totals["cached_input_tokens"] += node.get("cached_input_tokens") or 0
            if "output_tokens" in node:
                totals["output_tokens"] += node.get("output_tokens") or 0
            if "num_model_requests" in node:
                totals["requests"] += node.get("num_model_requests") or 0
            amount = node.get("amount")
            if isinstance(amount, dict) and amount.get("currency") in (None, "usd"):
                totals["cost_usd"] += amount.get("value") or 0
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(payload)
    return totals


def openai_snapshot(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    profile = load_profile(root, args.profile)
    path = Path(args.output).resolve() if args.output else default_report_path(root, profile, args.ticket)
    path.parent.mkdir(parents=True, exist_ok=True)
    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        raise SystemExit(f"missing provider API key env var: {args.api_key_env}")

    group_by = args.group_by or []
    common_params: dict[str, Any] = {
        "start_time": args.start_time,
        "end_time": args.end_time,
        "bucket_width": args.bucket_width,
    }
    if group_by:
        common_params["group_by"] = group_by

    usage_payload = openai_get(args.base_url, args.usage_path, api_key, common_params)
    costs_payload = openai_get(args.base_url, args.costs_path, api_key, common_params)
    usage_totals = parse_provider_totals(usage_payload)
    cost_totals = parse_provider_totals(costs_payload)

    report = load_or_create_report(path, args.ticket, args.profile, root)
    checkpoint = {
        "timestamp": utc_now(),
        "window": f"{args.start_time}..{args.end_time or 'now'}",
        "phase": args.phase or "provider_reconciliation",
        "gate": args.gate,
        "agent": args.agent or "usage_harness",
        "process": "provider_snapshot",
        "repo": args.repo,
        "model": args.model,
        "tool": "provider_usage_cost_api",
        "mode": "provider_reconciled",
        "requests": int(usage_totals.get("requests") or 0),
        "input_tokens": int(usage_totals.get("input_tokens") or 0),
        "cached_input_tokens": int(usage_totals.get("cached_input_tokens") or 0),
        "output_tokens": int(usage_totals.get("output_tokens") or 0),
        "tool_calls": 0,
        "tool_sessions": 0,
        "cost_usd": cost_totals.get("cost_usd") if "cost_usd" in cost_totals else None,
        "confidence": "provider_reconciled",
        "source": "OpenAI organization usage/costs API",
        "note": args.note or "Provider usage/cost APIs may lag and may not map perfectly to a single ticket unless isolated by project/API key/window.",
    }
    report.setdefault("checkpoints", []).append(checkpoint)
    snapshots = report.setdefault("provider_snapshots", [])
    snapshot: dict[str, Any] = {
        "timestamp": checkpoint["timestamp"],
        "provider": "openai",
        "query": {
            "base_url": args.base_url,
            "usage_path": args.usage_path,
            "costs_path": args.costs_path,
            "start_time": args.start_time,
            "end_time": args.end_time,
            "bucket_width": args.bucket_width,
            "group_by": group_by,
            "api_key_env": args.api_key_env,
        },
        "usage_totals": dict(usage_totals),
        "cost_totals": dict(cost_totals),
    }
    if args.store_raw:
        snapshot["raw_usage_response"] = usage_payload
        snapshot["raw_costs_response"] = costs_payload
    snapshots.append(snapshot)
    report["updated_at"] = utc_now()
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(format_checkpoint(checkpoint, path))
    return 0


def summary(args: argparse.Namespace) -> int:
    path = Path(args.file).resolve()
    report = load_json(path)
    markdown = markdown_summary(report)
    if args.markdown_output:
        out = Path(args.markdown_output).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown)
        print(f"wrote {out}")
    else:
        print(markdown, end="")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    cp = sub.add_parser("checkpoint", help="Append a usage/cost checkpoint")
    cp.add_argument("--root", default=".")
    cp.add_argument("--profile", required=True)
    cp.add_argument("--ticket", required=True)
    cp.add_argument("--output")
    cp.add_argument("--window")
    cp.add_argument("--phase")
    cp.add_argument("--gate")
    cp.add_argument("--agent")
    cp.add_argument("--process")
    cp.add_argument("--repo")
    cp.add_argument("--model")
    cp.add_argument("--tool")
    cp.add_argument("--mode", choices=sorted(VALID_MODES), required=True)
    cp.add_argument("--requests", type=int, default=0)
    cp.add_argument("--input-tokens", type=int, default=0)
    cp.add_argument("--cached-input-tokens", type=int, default=0)
    cp.add_argument("--output-tokens", type=int, default=0)
    cp.add_argument("--tool-calls", type=int, default=0)
    cp.add_argument("--tool-sessions", type=int, default=0)
    cp.add_argument("--cost-usd", type=float)
    cp.add_argument("--input-rate-per-mtok", type=float)
    cp.add_argument("--cached-input-rate-per-mtok", type=float)
    cp.add_argument("--output-rate-per-mtok", type=float)
    cp.add_argument("--tool-cost-usd", type=float)
    cp.add_argument("--confidence")
    cp.add_argument("--source")
    cp.add_argument("--note")
    cp.set_defaults(func=add_checkpoint)

    sm = sub.add_parser("summary", help="Print or write a markdown summary")
    sm.add_argument("--file", required=True)
    sm.add_argument("--markdown-output")
    sm.set_defaults(func=summary)

    op = sub.add_parser("openai-snapshot", help="Append a provider-reconciled OpenAI Usage/Costs snapshot")
    op.add_argument("--root", default=".")
    op.add_argument("--profile", required=True)
    op.add_argument("--ticket", required=True)
    op.add_argument("--output")
    op.add_argument("--start-time", type=int, required=True, help="Unix seconds, inclusive")
    op.add_argument("--end-time", type=int, help="Unix seconds, exclusive/endpoint-defined")
    op.add_argument("--bucket-width", default="1d")
    op.add_argument("--group-by", action="append", default=[])
    op.add_argument("--base-url", default="https://api.openai.com")
    op.add_argument("--usage-path", default="/v1/organization/usage/completions")
    op.add_argument("--costs-path", default="/v1/organization/costs")
    op.add_argument("--api-key-env", default="OPENAI_ADMIN_KEY")
    op.add_argument("--phase")
    op.add_argument("--gate")
    op.add_argument("--agent")
    op.add_argument("--repo")
    op.add_argument("--model")
    op.add_argument("--note")
    op.add_argument("--store-raw", action="store_true", help="Store raw provider responses; avoid if they contain sensitive metadata")
    op.set_defaults(func=openai_snapshot)
    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
