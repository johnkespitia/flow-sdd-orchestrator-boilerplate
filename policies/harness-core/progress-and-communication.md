# Progress, Retry, and Hypercommunication

## Progress updates

Long-running processes should be observable while they run. Do not hide retry
loops or repeated polling until final closeout.

```md
Progress update:
- Phase:
- Completed:
- Current step:
- Retry/repeat:
- Reason:
- Continuing with:
- Blocked only if:
```

Continue normal non-destructive retries without confirmation. Pause for real
approval gates, destructive actions, security/credential risk, unusual cost or
rate-limit risk, merge/deploy approval, or when no safe alternate path remains.

## Hypercommunication

Meaningful state changes should be reflected in the surfaces stakeholders use.
Profiles define the concrete surfaces, but the core events are:

- phase changes
- blockers
- open questions blocking or cleared
- R1/R2/R3/R4/R5 verdicts
- implementation complete / not-ready reasons
- validation passed/failed/rerun
- ready for review / merge / deploy
- closeout and follow-ups

If direct posting is unavailable, draft exact text and record the intended
surface in the communication ledger.
