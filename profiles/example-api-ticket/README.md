# Example API Ticket Profile

Spanish mirror: [profiles/example-api-ticket/README.es.md](./README.es.md)

This is a generic example profile safe for open-source documentation. It is not
bound to any private organization.

Use it as a template to create your own private profile with local labels,
repository naming, ticket keys, and automation commands.

## Usage and cost telemetry

This example profile enables usage/cost checkpoints during long-running work,
retries, agent handoffs, external tool runs, validation/deploy runs, and
closeout. Reports must mark every value as `exact`, `provider_reconciled`, or
`estimated`.

```bash
python3 scripts/harness/usage_report.py checkpoint --ticket PROJ-123 --profile example-api-ticket --phase G1 --agent research_agent --mode estimated --note "research checkpoint"
python3 scripts/harness/usage_report.py summary --file docs/evidence/proj-123-usage-and-cost.json
# Optional provider reconciliation when an admin API key is configured:
python3 scripts/harness/usage_report.py openai-snapshot --ticket PROJ-123 --profile example-api-ticket --start-time <unix-seconds> --group-by model --group-by project_id
```
