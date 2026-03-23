---
name: softos-foundation-alignment
description: "Use when auditing existing in-flight projects to align them with SoftOS: detect what to copy/reuse/remove, generate foundation specs, enforce coding style/test contracts, install required skills, and create missing runtime/capability packs."
---

# SoftOS Foundation Alignment

Use this skill for projects "on the way" that must be aligned to the SoftOS operating model.

## What this skill produces

- A concrete audit of current project assets with decision tags:
  - `copy` (adopt as-is)
  - `reuse` (adopt with adjustments)
  - `remove` (deprecate / no migrar)
- A foundation spec pack under `specs/000-foundation/**`.
- Runtime, capability, and agent-skill alignment per repo.
- Docker Compose aligned with exposed ports for implementation repos that require host access.
- Validation gates ready (`spec review`, `spec approve`, `ci spec`).

## Required Inputs

- Workspace root path.
- Target implementation repo(s) and path(s).
- Runtime(s) currently used and desired end-state.
- Any existing coding standards or architecture docs.

If input is missing, infer from repository structure and `workspace.config.json`.

## Spec Taxonomy

Use this directory contract to place specs correctly:

- `specs/000-foundation/**`: workspace operating model and SDLC/governance contracts.
- `specs/domains/**`: business-domain contracts, invariants, and stable rules shared by multiple features.
- `specs/features/**`: concrete implementable changes with scoped `targets`.

## Execution Workflow

### 1) Preflight and workspace health

Run:

```bash
scripts/preflight_env.sh --build
# Optional: apply migration/apply commands configured per repo in workspace.preflight.json
scripts/preflight_env.sh --build --run-migrations
python3 ./flow doctor
python3 ./flow skills doctor
python3 ./flow ci spec --all
```

If `flow ci spec --all` fails, do not block discovery; continue with audit and return findings.

`preflight_env.sh` is policy-driven and technology-agnostic. Define repo-specific readiness/migration/env checks in `workspace.preflight.json`.

### 2) Inventory and classify project assets

Use the checklist in `references/audit-matrix.md`.

Minimum scan:

```bash
rg --files <repo_path>
rg -n "TODO|FIXME|deprecated|legacy|@deprecated|console\\.log|var_dump|dd\\(" -S <repo_path>
rg -n "phpunit|pest|pytest|jest|vitest|go test|docker-compose|Dockerfile|Makefile|CI|workflow" -S <repo_path>
```

Create an explicit decision matrix per area:

- entrypoints / routing
- domain entities and services
- adapters/integrations
- tests
- CI and release hooks
- infra and runtime assumptions
- coding style and static analysis

Output each row as:

`<artifact> -> copy|reuse|remove + rationale + target path`

### 3) Map repo to runtime and skills

Resolve current context:

```bash
python3 ./flow skills context --repo <repo_id> --json
```

If missing skills are needed:

```bash
python3 ./flow skills discover <query> --limit 10 --json
python3 ./flow skills install <identifier> --provider <tessl|skills-sh> --name <workspace/skill-name> --runtime <runtime>
python3 ./flow skills doctor
```

Rules:

- Keep runtime-level skills in `runtimes/<runtime>.runtime.json` under `agent_skill_refs`.
- Keep workspace skill entries in `workspace.skills.json`.
- Ensure every `agent_skill_refs` entry resolves to a manifest entry.

### 4) Create or adjust runtime packs (when missing)

If target runtime does not exist in `workspace.runtimes.json`:

1. Add `runtimes/<new-runtime>.runtime.json`.
2. Register it in `workspace.runtimes.json`.
3. Include: `target_roots`, `default_targets`, `test_runner`, `test_hint`, `test_required_roots`, `agent_skill_refs`, `ci`, and `compose` as applicable.

Use detailed guidance in `references/runtime-capability-playbook.md`.

### 4.1) Expose ports in Docker Compose when repo must be reachable

If the project needs host-accessible services (API/web/dev server), ensure explicit port exposure.

Preferred path:

```bash
python3 ./flow add-project <repo_id> --runtime <runtime> --path <path> --port <host_port>
```

For existing repos already registered, ensure runtime `compose.default_port` is defined and re-run stack apply/update as needed.

After changes:

```bash
python3 ./flow stack up
python3 ./flow stack ps
```

Validate that service appears with `0.0.0.0:<host_port>-><container_port>/tcp`.

Then validate application readiness (not just container state):

```bash
python3 ./flow stack exec <compose_service> -- sh -lc "<runtime readiness command>"
curl -fsS http://127.0.0.1:<host_port>/healthz || curl -fsS http://127.0.0.1:<host_port>/
```

Treat `container up + app down` as a failed alignment.

### 5) Create or adjust capability packs (when missing)

If framework/domain capability is required and absent:

1. Add `capabilities/<new-capability>.capability.json`.
2. Register it in `workspace.capabilities.json`.
3. Include: `required_runtimes`, `target_roots`, `agent_skill_refs`, `placeholder_files`, and `compose_override` if needed.

Keep capability packs additive and minimal.

### 6) Create the foundation spec pack

Use `references/foundation-spec-pack.md`.

Create at least these specs:

1. `<project>-foundation-alignment.spec.md`
2. `<project>-coding-style-and-quality-contract.spec.md`
3. `<project>-runtime-capability-skill-governance.spec.md`

All specs must:

- live in `specs/000-foundation/`
- include valid `targets`
- declare `required_runtimes` / `required_capabilities` as needed
- include explicit acceptance criteria
- include `[@test]` references per affected repo

Important:

- If real tests do not exist yet, create minimal valid test placeholders in the target repo to satisfy spec governance.

### 7) Align style and test contracts into foundation specs

Each project-level foundation spec must codify:

- naming conventions
- lint/format/static analysis commands
- test taxonomy (unit/integration/e2e/smoke)
- minimum CI gates by repo/runtime
- definition of done for slices

Do not keep style rules only in README or tribal knowledge.

### 8) Run governance gates

For each created/updated foundation spec:

```bash
python3 ./flow spec review <slug>
python3 ./flow spec approve <slug> --approver <id>
python3 ./flow ci spec <slug>
```

If failures occur, patch spec and/or referenced test files until green.

### 9) Final handoff report

Return:

- asset decision matrix (`copy|reuse|remove`)
- created/updated specs
- installed skills
- runtime/capability changes
- commands executed and status
- open risks and follow-up slices

## Non-negotiable Rules

- `specs/**` is the source of truth.
- No implementation beyond declared `targets`.
- Keep foundation specs testable by governance gates.
- Do not leave unresolved skill/runtime/capability references in manifests.
- If a repo requires inbound host traffic, do not leave compose without explicit port mapping.
- Do not mark a repo as running unless container status and app readiness checks are both passing.

## Reference Files

- `references/audit-matrix.md`
- `references/foundation-spec-pack.md`
- `references/runtime-capability-playbook.md`
