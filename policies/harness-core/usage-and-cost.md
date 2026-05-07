# Usage and Cost Harness

The Usage and Cost Harness makes agent work observable from a spend and token
consumption perspective. It is a reporting and budget-control layer for any
profile that runs model, tool, or automation work.

## Signal classes

Every usage value must declare one of these modes:

- `exact` — captured directly from the request/response or tool runtime that
  produced the usage.
- `provider_reconciled` — read from a provider usage/cost API, dashboard, or
  invoice-aligned report for a time window, project, API key, user, or model.
- `estimated` — computed from local token counting, transcript size, elapsed
  runtime, or manual input because exact usage is not exposed locally.

Never mix these modes without labeling them. A final report may contain all
three, but it must show which totals are exact, provider-reconciled, and
estimated.

## Checkpoints

Profiles should emit usage checkpoints at meaningful boundaries:

- process/session start
- phase or gate start/end
- long-running loop progress update
- retry/rerun
- agent handoff
- external tool run
- validation/deploy run
- closeout

A checkpoint should include:

```md
Usage update:
- Window:
- Phase/gate:
- Agent/process:
- Mode: exact / provider_reconciled / estimated
- Requests:
- Input tokens:
- Cached input tokens:
- Output tokens:
- Tool calls/sessions:
- Cost:
- Budget used:
- Confidence:
- Notes/caveats:
```

## Budget gates

Usage telemetry is advisory unless a profile marks it blocking.

Recommended default behavior:

- warn when estimated or reconciled spend reaches the profile warning threshold
- pause before continuing when a hard cap is reached
- continue without confirmation for low-cost, non-destructive retries below the
  warning threshold
- require explicit approval for unusually expensive research, repeated failures,
  or external tools with separate billable line items

## Final report

Closeout must include a final usage report when the profile enables this
harness. The report should break down consumption by:

- ticket/work item
- phase/gate
- agent/process
- model/provider
- tool or external service
- repo/slice when available
- mode (`exact`, `provider_reconciled`, `estimated`)

The final report must include caveats for provider lag, missing per-turn usage,
or estimates that cannot be reconciled.

## Evidence and privacy

Usage evidence must not contain secrets, raw API keys, private prompts,
customer data, or sensitive chat transcripts. Store identifiers as aliases or
redacted IDs. If provider APIs are queried, record the query window and grouping
but not credentials.
