# Audit Matrix

Use this matrix during project intake for SoftOS alignment.

## 1. Artifact Inventory

| Area | Artifact | Current Path | Observed State | Decision (`copy`/`reuse`/`remove`) | Target Path | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Entrypoints |  |  |  |  |  |  |
| Domain |  |  |  |  |  |  |
| Persistence |  |  |  |  |  |  |
| Integrations |  |  |  |  |  |  |
| UI/API Contracts |  |  |  |  |  |  |
| Tests |  |  |  |  |  |  |
| CI/CD |  |  |  |  |  |  |
| Infra |  |  |  |  |  |  |
| Tooling/Style |  |  |  |  |  |  |

## 2. Decision Rules

- `copy`: no material change needed; directly reusable.
- `reuse`: reusable with constrained adaptation; track adaptation in a feature spec.
- `remove`: conflicts with SoftOS model, duplicates existing capability, or is dead code.

## 3. Red Flags (must be explicit in findings)

- Multiple competing entrypoints for same flow.
- Hidden runtime dependencies not declared in manifests.
- Tests that are not runnable from CI.
- Style/lint rules applied manually only.
- Prod-only behavior with no spec coverage.
- Deprecated code still referenced by active paths.

## 4. Output Contract

For each row, include one rationale sentence and one concrete next action.

Format:

`<artifact> -> <decision> because <reason>. Next: <action>.`
